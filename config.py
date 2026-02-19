import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'redline.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-Mail configuration
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@redline.local")
    WORKSHOP_EMAIL = os.environ.get("WORKSHOP_EMAIL", "werkstatt@redline.local")

    # FileMaker REST API
    FILEMAKER_HOST = os.environ.get("FILEMAKER_HOST", "https://filemaker.redline.local")
    FILEMAKER_DATABASE = os.environ.get("FILEMAKER_DATABASE", "RedlineDB")
    FILEMAKER_USERNAME = os.environ.get("FILEMAKER_USERNAME", "admin")
    FILEMAKER_PASSWORD = os.environ.get("FILEMAKER_PASSWORD", "")

    # QR Code base URL – the public URL where this app is hosted
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    # Static folder for generated QR images
    QR_CODE_DIR = os.path.join(BASE_DIR, "static", "qrcodes")

    # Defect categories
    DEFECT_CATEGORIES = [
        "Mechanischer Schaden",
        "Elektrischer Fehler",
        "Softwareproblem",
        "Gehäuseschaden",
        "Kabelproblem",
        "Displayschaden",
        "Akkuproblem",
        "Wasserschaden",
        "Sonstiges",
    ]
