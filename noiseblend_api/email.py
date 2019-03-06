from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Email, Mail, Personalization, Substitution

from . import config


def send_confirmation_email(email, username, confirmation_token):
    sg = SendGridAPIClient(apikey=config.sendgrid.apikey)

    mail = Mail()
    mail.template_id = config.sendgrid.template_id
    mail.from_email = Email(config.sendgrid.sender)
    mail.subject = "Confirmation email"

    pers = Personalization()
    pers.add_to(Email(email))
    pers.add_substitution(Substitution(r"-confirmation_token-", confirmation_token))
    pers.add_substitution(Substitution(r"%username%", username))

    mail.add_personalization(pers)

    sg.client.mail.send.post(request_body=mail.get())
