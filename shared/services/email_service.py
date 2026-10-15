import smtplib
import socket
from email.message import EmailMessage


class EmailSendError(Exception):
    """Raised when an email could not be sent. The message is safe to show to users."""


class NoInternetError(EmailSendError):
    """Raised when an email could not be sent because there is no internet
    connection (DNS lookup failure, connection refused, timed out, etc.)."""


# How long to wait when trying to reach the SMTP server before giving up
# and treating it as a connectivity problem, instead of hanging forever
# when there is no internet connection.
_SMTP_TIMEOUT_SECONDS = 15


def _as_send_error(exc):
    """Translate a low-level exception from smtplib/socket into an
    EmailSendError (or the more specific NoInternetError) with a
    user-friendly message.

    Note: smtplib's exceptions (e.g. SMTPAuthenticationError) subclass
    OSError in Python's standard library, so they must be checked for
    *before* the generic OSError/connectivity check below - otherwise a
    rejected password would incorrectly be reported as "no internet".
    """
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return EmailSendError(
            "Could not send email: the email account's credentials were rejected."
        )
    if isinstance(exc, smtplib.SMTPResponseException):
        # The mail server responded, so the connection itself worked fine -
        # this is a protocol-level error, not a connectivity problem.
        return EmailSendError(f"Could not send email: {exc}")
    if isinstance(exc, (socket.gaierror, TimeoutError, ConnectionError, OSError)):
        return NoInternetError(
            "Could not send email: no internet connection. "
            "Please check your network connection and try again."
        )
    return EmailSendError(f"Could not send email: {exc}")


def email(from_address, to_address, subject, message, app_password):
    msg = EmailMessage()

    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = to_address

    msg.set_content(message)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=_SMTP_TIMEOUT_SECONDS) as server:
            server.starttls()

            server.login(
                from_address,
                app_password
            )

            server.send_message(msg)
    except Exception as e:
        print(f'ERROR:{e}')
        raise _as_send_error(e) from e

def email_file(from_address,to_address,subject,message,file_name,app_password):
    msg = EmailMessage()

    msg["Subject"] =subject
    msg["From"] = from_address
    msg["To"] = to_address

    try:
        with open(file_name, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="text",
                subtype="plain",
                filename=file_name
            )

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=_SMTP_TIMEOUT_SECONDS) as server:
            server.starttls()

            server.login(
                from_address,
                app_password
            )

            server.send_message(msg)
    except Exception as e:
        print(f'ERROR:{e}')
        raise _as_send_error(e) from e
