"""
Redline – Configuration management.

Three environment classes are provided:
  DevelopmentConfig  (FLASK_ENV=development, the default)
  ProductionConfig   (FLASK_ENV=production)
  TestConfig         (TESTING=True, used by pytest)

Select via the FLASK_ENV environment variable, or pass the class directly
to create_app().
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

_DEFAULT_SECRET = "change-me-in-production-secret-key"

# Application version – read from the VERSION file at the project root
_version_file = os.path.join(BASE_DIR, "VERSION")
APP_VERSION: str = (
    open(_version_file).read().strip() if os.path.exists(_version_file) else "unknown"
)


class Config:
    """Base configuration shared by all environments."""

    # ------------------------------------------------------------------ #
    #  Flask core                                                          #
    # ------------------------------------------------------------------ #
    SECRET_KEY: str = os.environ.get("SECRET_KEY", _DEFAULT_SECRET)

    # ------------------------------------------------------------------ #
    #  Database                                                            #
    # ------------------------------------------------------------------ #
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'redline.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_pre_ping": True,  # auto-reconnect on stale connections
    }

    # ------------------------------------------------------------------ #
    #  Flask-Mail                                                          #
    # ------------------------------------------------------------------ #
    MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT: int = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS: bool = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "")
    MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER: str = os.environ.get(
        "MAIL_DEFAULT_SENDER", "noreply@redline.local"
    )
    WORKSHOP_EMAIL: str = os.environ.get("WORKSHOP_EMAIL", "werkstatt@redline.local")

    # ------------------------------------------------------------------ #
    #  FileMaker REST API (optional integration)                           #
    # ------------------------------------------------------------------ #
    FILEMAKER_HOST: str = os.environ.get(
        "FILEMAKER_HOST", "https://filemaker.redline.local"
    )
    FILEMAKER_DATABASE: str = os.environ.get("FILEMAKER_DATABASE", "RedlineDB")
    FILEMAKER_USERNAME: str = os.environ.get("FILEMAKER_USERNAME", "admin")
    FILEMAKER_PASSWORD: str = os.environ.get("FILEMAKER_PASSWORD", "")

    # ------------------------------------------------------------------ #
    #  QR codes                                                            #
    # ------------------------------------------------------------------ #
    # Public URL where this app is accessible (used for QR code URLs).
    # MUST be set to a reachable host in production.
    APP_BASE_URL: str = os.environ.get("APP_BASE_URL", "http://localhost:5000")

    # Static folder for generated QR images
    QR_CODE_DIR: str = os.path.join(BASE_DIR, "static", "qrcodes")

    # ------------------------------------------------------------------ #
    #  Photo uploads (werkstatt comments + defect reports)                 #
    # ------------------------------------------------------------------ #
    UPLOAD_FOLDER: str = os.path.join(BASE_DIR, "static", "uploads")
    # Flask enforces this limit and returns 413 automatically
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16 MB
    ALLOWED_PHOTO_EXTENSIONS: set = {"jpg", "jpeg", "png", "gif", "webp"}

    # ------------------------------------------------------------------ #
    #  Rate limiting (flask-limiter)                                       #
    # ------------------------------------------------------------------ #
    RATELIMIT_ENABLED: bool = True
    RATELIMIT_STORAGE_URL: str = os.environ.get("RATELIMIT_STORAGE_URL", "memory://")
    RATELIMIT_DEFAULT: str = "200 per hour;50 per minute"

    # ------------------------------------------------------------------ #
    #  Seed / domain data                                                  #
    # ------------------------------------------------------------------ #
    DEFECT_CATEGORIES: list = [
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

    # ------------------------------------------------------------------ #
    #  Validation                                                          #
    # ------------------------------------------------------------------ #
    @classmethod
    def validate(cls) -> None:
        """
        Validate the configuration.  Called by the app factory before
        starting.  Sub-classes may add stricter checks (e.g. enforcing HTTPS).
        """
        if cls.SECRET_KEY == _DEFAULT_SECRET:
            print(
                "[WARNING] SECRET_KEY is set to the default placeholder value.\n"
                "         Generate a secure key with:\n"
                "         python -c \"import secrets; print(secrets.token_hex(32))\"\n"
                "         and set it as SECRET_KEY in your .env file.",
                file=sys.stderr,
            )

        if "localhost" in cls.APP_BASE_URL:
            print(
                "[WARNING] APP_BASE_URL is set to localhost.\n"
                "         QR codes will only work on this machine.\n"
                "         Set APP_BASE_URL to the public server address in .env.",
                file=sys.stderr,
            )


class DevelopmentConfig(Config):
    """Local development – debug on, relaxed validation."""

    DEBUG: bool = True
    SQLALCHEMY_ECHO: bool = False  # set True to log all SQL
    SHOW_DEBUG_INFO: bool = True  # show system-info card in help page


class ProductionConfig(Config):
    """Production – strict validation, debug off."""

    DEBUG: bool = False
    SHOW_DEBUG_INFO: bool = False  # never expose system info in production

    @classmethod
    def validate(cls) -> None:
        errors: list[str] = []

        if cls.SECRET_KEY == _DEFAULT_SECRET:
            errors.append(
                "SECRET_KEY must be changed from the default placeholder value.\n"
                "  Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

        if "localhost" in cls.APP_BASE_URL:
            errors.append(
                "APP_BASE_URL must not point to localhost in production.\n"
                "  Set it to the public URL of this server."
            )

        if not cls.APP_BASE_URL.startswith("https://"):
            errors.append(
                "APP_BASE_URL should use HTTPS in production to keep QR code\n"
                "  links secure.  Current value: " + cls.APP_BASE_URL
            )

        if errors:
            print("\n[PRODUCTION CONFIGURATION ERRORS]", file=sys.stderr)
            for i, err in enumerate(errors, 1):
                print(f"  {i}. {err}", file=sys.stderr)
            print("", file=sys.stderr)
            sys.exit(1)


class TestConfig(Config):
    """Test environment – in-memory DB, CSRF + rate-limiting disabled."""

    TESTING: bool = True
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"
    WTF_CSRF_ENABLED: bool = False
    SECRET_KEY: str = "test-secret-key-do-not-use-in-production"
    MAIL_SUPPRESS_SEND: bool = True
    APP_BASE_URL: str = "http://testserver"
    QR_CODE_DIR: str = "/tmp/test_redline_qrcodes"
    UPLOAD_FOLDER: str = "/tmp/test_redline_uploads"
    RATELIMIT_ENABLED: bool = False  # never throttle tests
    SHOW_DEBUG_INFO: bool = False


# Mapping used by create_app() when selecting config via FLASK_ENV
config_by_name: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestConfig,
    "default": DevelopmentConfig,
}
