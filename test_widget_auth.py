import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch


_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEMP_DIR.name}/widget-test.db"
os.environ["CSR_DATABASE_URL"] = f"sqlite:///{_TEMP_DIR.name}/widget-csr-test.db"
os.environ["CHATBOT_VERIFY_BASE_URL"] = "https://beta-tj1.frontlineticketing.com"
os.environ["CHATBOT_SERVICE_SECRET"] = "682be0af23d4bdf216504fa2778398475c75214670adf8dabac4a3bd4158fceb"

from app import (  # noqa: E402
    Business,
    ChatSession,
    User,
    WidgetApiLog,
    app,
    db,
)


def json_response(status_code, payload):
    response = Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.json.return_value = payload
    return response


class WidgetAuthenticationTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        with app.app_context():
            db.drop_all()
            db.create_all()
            owner = User(
                first_name="Widget",
                last_name="Owner",
                email="owner@example.test",
                password_hash="not-used",
            )
            db.session.add(owner)
            db.session.flush()
            business = Business(
                user_id=owner.id,
                name="Test Business",
                authorized_domains="localhost",
                widget_key="widget-test-key",
                csr_key="csr-test-key",
                n8n_instance_id="test-instance",
                external_csr_api_endpoint="https://csr.example.test",
                chatbot_verify_base_url="https://beta-tj1.frontlineticketing.com",
                chatbot_service_secret="682be0af23d4bdf216504fa2778398475c75214670adf8dabac4a3bd4158fceb",
            )
            db.session.add(business)
            db.session.commit()

        self.client = app.test_client()

    def test_anonymous_validation_returns_anonymous_mode(self):
        response = self.client.post(
            "/validate_widget",
            json={
                "widget_key": "widget-test-key",
                "domain": "localhost",
                "visitor_id": "anonymous-visitor",
                "auth": {"mode": "anonymous", "token": None},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["authentication"], {"mode": "anonymous", "user": None})

    @patch("app.requests.post")
    def test_authenticated_chat_verifies_against_flt_and_stores_user(self, post_mock):
        post_mock.side_effect = [
            json_response(
                200,
                {
                    "valid": True,
                    "user": {
                        "id": 123,
                        "name": "Test Customer",
                        "email": "customer@example.test",
                    },
                },
            ),
            json_response(200, {"output": "Hello from the bot"}),
        ]

        response = self.client.post(
            "/api/chat",
            json={
                "message": "Hello",
                "widget_key": "widget-test-key",
                "visitor_id": "authenticated-visitor",
                "user_type": "buyer",
                "auth": {
                    "mode": "authenticated",
                    "token": "valid-user-token",
                },
            },
            headers={"Origin": "http://localhost:3000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["auth_mode"], "authenticated")
        verify_call = post_mock.call_args_list[0]
        self.assertEqual(
            verify_call.args[0],
            "https://beta-tj1.frontlineticketing.com/api/chatbot/verify",
        )
        self.assertEqual(verify_call.kwargs["json"], {"token": "valid-user-token"})
        self.assertEqual(
            verify_call.kwargs["headers"]["X-Service-Secret"],
            "682be0af23d4bdf216504fa2778398475c75214670adf8dabac4a3bd4158fceb",
        )

        with app.app_context():
            chat_session = ChatSession.query.filter_by(user_identifier="authenticated-visitor").one()
            self.assertEqual(chat_session.auth_mode, "authenticated")
            self.assertEqual(chat_session.authenticated_user_id, "123")
            self.assertEqual(json.loads(chat_session.authenticated_user_data)["name"], "Test Customer")
            self.assertNotEqual(chat_session.auth_token_fingerprint, "valid-user-token")

            request_log = WidgetApiLog.query.filter_by(endpoint="/api/chat").one()
            self.assertNotIn("valid-user-token", request_log.request_payload)
            self.assertIn("[REDACTED]", request_log.request_payload)

    @patch("app.requests.post")
    def test_invalid_authenticated_token_is_rejected(self, post_mock):
        post_mock.return_value = json_response(200, {"valid": False})

        response = self.client.post(
            "/api/chat",
            json={
                "message": "Hello",
                "widget_key": "widget-test-key",
                "visitor_id": "rejected-visitor",
                "user_type": "buyer",
                "auth": {
                    "mode": "authenticated",
                    "token": "wrong-token",
                },
            },
        )

        self.assertEqual(response.status_code, 401)
        with app.app_context():
            self.assertIsNone(ChatSession.query.filter_by(user_identifier="rejected-visitor").first())


if __name__ == "__main__":
    unittest.main()
