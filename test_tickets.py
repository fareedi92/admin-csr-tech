import sys
import os
sys.path.append('/home/ubuntu/new_admin/flt_csr_app_ai')
from app import app, db, Ticket, TicketMessage

with app.app_context():
    ticket = Ticket.query.first()
    if ticket:
        print("Ticket:", ticket.id)
        latest_message = max(ticket.messages or [], key=lambda message: (message.created_at, message.id), default=None)
        print("Latest message sender type:", latest_message.sender_type if latest_message else None)
