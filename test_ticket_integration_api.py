import os
import tempfile
import unittest


_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEMP_DIR.name}/ticket-integration-test.db"
os.environ["TICKETS_API_KEY"] = "integration-test-secret"

from app import (  # noqa: E402
    AdminAccount,
    ChatConversation,
    Ticket,
    TicketStatus,
    User,
    app,
    backfill_chat_external_user_ids,
    db,
)


class TicketIntegrationApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        with app.app_context():
            db.drop_all()
            db.create_all()

            csr = User(
                email="csr@example.test",
                password_hash="test",
                display_name="CSR",
                role="csr",
            )
            admin = AdminAccount(
                email="admin@example.test",
                password_hash="test",
                display_name="Admin",
            )
            db.session.add_all([csr, admin])
            db.session.flush()

            for status_data in TicketStatus.get_default_statuses():
                db.session.add(TicketStatus(**status_data))

            user_chat = ChatConversation(
                external_chat_id="chat-user-123",
                customer_name="Buyer One",
                customer_external_user_id="user-123",
            )
            other_chat = ChatConversation(
                external_chat_id="chat-user-456",
                customer_name="Buyer Two",
                customer_external_user_id="user-456",
            )
            db.session.add_all([user_chat, other_chat])
            db.session.flush()

            db.session.add_all([
                Ticket(
                    ticket_number="TCK_1001",
                    title="Buyer ticket",
                    origin="csr",
                    created_by_csr_id=csr.id,
                    chat_id=user_chat.id,
                ),
                Ticket(
                    ticket_number="TCK_1002",
                    title="Other buyer ticket",
                    origin="csr",
                    created_by_csr_id=csr.id,
                    chat_id=other_chat.id,
                ),
                Ticket(
                    ticket_number="TCK_1003",
                    title="Admin ticket",
                    origin="admin",
                    created_by_admin_id=admin.id,
                ),
            ])
            db.session.commit()

        self.client = app.test_client()
        self.headers = {"X-Service-Secret": "integration-test-secret"}

    def test_credentials_are_required(self):
        response = self.client.get("/api/integration/tickets")
        self.assertEqual(response.status_code, 401)

    def test_get_all_tickets(self):
        response = self.client.get("/api/integration/tickets", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 3)

    def test_get_tickets_for_external_user(self):
        response = self.client.get(
            "/api/integration/tickets/users/user-123",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["tickets"][0]["ticket_number"], "TCK_1001")
        self.assertEqual(
            payload["tickets"][0]["customer_external_user_id"],
            "user-123",
        )

    def test_get_tickets_by_user_id_query_param(self):
        response = self.client.get(
            "/api/integration/tickets?user_id=user-123",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["tickets"][0]["ticket_number"], "TCK_1001")
        self.assertEqual(payload["filters"]["customer_external_user_id"], "user-123")

    def test_get_admin_generated_tickets(self):
        response = self.client.get(
            "/api/integration/tickets/admin-generated",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["tickets"][0]["origin"], "admin")
        self.assertTrue(payload["tickets"][0]["is_admin_generated"])

    def test_backfills_legacy_authenticated_user_link(self):
        with app.app_context():
            legacy_chat = ChatConversation(
                external_chat_id="legacy-chat",
                customer_name="Legacy Buyer",
                authenticated_user_data='{"id": "legacy-user"}',
            )
            db.session.add(legacy_chat)
            db.session.commit()

            backfill_chat_external_user_ids()

            self.assertEqual(
                legacy_chat.customer_external_user_id,
                "legacy-user",
            )

    def test_user_can_update_own_ticket_status(self):
        response = self.client.post(
            "/api/integration/tickets/TCK_1001/status",
            headers=self.headers,
            json={"user_id": "user-123", "status": "closed", "notes": "Issue fixed"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["ticket"]["status"], "closed")
        self.assertEqual(payload["ticket"]["ticket_number"], "TCK_1001")
        self.assertIsNotNone(payload["ticket"]["resolved_at"])

    def test_user_cannot_update_someone_elses_ticket(self):
        response = self.client.post(
            "/api/integration/tickets/TCK_1002/status",
            headers=self.headers,
            json={"user_id": "user-123", "status": "closed"},
        )
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_update_admin_ticket(self):
        response = self.client.post(
            "/api/integration/tickets/TCK_1003/status",
            headers=self.headers,
            json={"user_id": "user-123", "status": "closed"},
        )
        self.assertEqual(response.status_code, 403)

    def test_status_update_accepts_json_sent_as_plain_text(self):
        headers = {
            **self.headers,
            "Content-Type": "text/plain",
        }
        response = self.client.post(
            "/api/integration/tickets/TCK_1001/status",
            headers=headers,
            data='{"user_id":"user-123","status":"closed"}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ticket"]["status"], "closed")


if __name__ == "__main__":
    unittest.main()
