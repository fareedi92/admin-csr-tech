import os
import tempfile
import unittest


_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEMP_DIR.name}/chatbot-auth-test.db"
os.environ.pop("CHATBOT_SERVICE_SECRET", None)
os.environ.pop("CHATBOT_TEST_TOKEN", None)

from app import ChatConversation, app, db  # noqa: E402


class ChatbotHandoffAuthTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        with app.app_context():
            db.drop_all()
            db.create_all()
        self.client = app.test_client()

    def test_authenticated_handoff_stores_customer_identity(self):
        response = self.client.post(
            "/init",
            json={
                "visitor_id": "visitor-123",
                "transcript": [],
                "authentication": {
                    "mode": "authenticated",
                    "user": {
                        "id": "user-123",
                        "name": "Test Customer",
                        "email": "customer@example.test",
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        with app.app_context():
            chat = ChatConversation.query.filter_by(external_chat_id="visitor-123").one()
            self.assertEqual(chat.auth_mode, "authenticated")
            self.assertEqual(chat.customer_external_user_id, "user-123")
            self.assertEqual(chat.customer_name, "Test Customer")
            self.assertEqual(chat.customer_email, "customer@example.test")

    def test_anonymous_handoff_defaults_to_anonymous(self):
        response = self.client.post(
            "/init",
            json={
                "visitor_id": "visitor-anon",
                "transcript": [],
                "authentication": {"mode": "anonymous", "user": None},
            },
        )

        self.assertEqual(response.status_code, 200)
        with app.app_context():
            chat = ChatConversation.query.filter_by(external_chat_id="visitor-anon").one()
            self.assertEqual(chat.auth_mode, "anonymous")
            self.assertIsNone(chat.customer_external_user_id)


if __name__ == "__main__":
    unittest.main()
