from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)
import os
from datetime import datetime
import re


app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 465
app.config["MAIL_USERNAME"] = "your_mail"
app.config["MAIL_PASSWORD"] = "your_password"
app.config["MAIL_USE_TLS"] = False
app.config["MAIL_USE_SSL"] = True


# Initialization of extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
mail = Mail(app)


# Database model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    surname = db.Column(db.String(100))
    birthdate = db.Column(db.Date)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    confirmed = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def get_confirmation_token(self, expiration=3600):
        s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        return s.dumps(self.email, salt="confirm-email")

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return self.confirmed

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    @staticmethod
    def verify_confirmation_token(token, expiration=3600):
        s = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        try:
            email = s.loads(token, salt="confirm-email", max_age=expiration)
        except:
            return None
        return User.query.filter_by(email=email).first()


@app.route("/")
def welcome():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    today = datetime.today().strftime("%Y-%m-%d")

    if request.method == "POST":
        name = request.form["name"]
        surname = request.form["surname"]
        birthdate = datetime.strptime(request.form["birthdate"], "%Y-%m-%d").date()
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        existing_user_by_email = User.query.filter_by(email=email).first()
        existing_user_by_username = User.query.filter_by(username=username).first()

        errors = []

        if birthdate > datetime.today().date():
            errors.append("Invalid birthdate. Please select a valid date.")
        if existing_user_by_email:
            errors.append("Email address already exists.")
        if existing_user_by_username:
            errors.append("Username already exists.")
        if password != confirm_password:
            errors.append("Passwords do not match.")

        password_pattern = re.compile(
            r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])[A-Za-z\d@$!%*?&#]{8,}$"
        )

        if not password_pattern.match(password):
            errors.append(
                "Password must be at least 8 characters, contain an uppercase letter, a lowercase letter, a number, and a special character."
            )

        if errors:
            for error in errors:
                flash(error)
            return render_template(
                "register.html",
                today=today,
                name=name,
                surname=surname,
                birthdate=str(birthdate),
                username=username,
                email=email,
            )
        else:
            user = User(
                username=username,
                email=email,
                name=name,
                surname=surname,
                birthdate=birthdate,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            token = user.get_confirmation_token()
            send_confirmation_email(user.email, token)

            flash("Successfully registered! Check your email to confirm your account.")
            return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form["identifier"]
        password = request.form["password"]

        user = User.query.filter(
            (User.email == identifier) | (User.username == identifier)
        ).first()

        if user:
            if user.check_password(password):
                if user.confirmed:
                    login_user(user)
                    return redirect(url_for("dashboard"))
                else:
                    flash(
                        "Account not confirmed. Check your email for the confirmation link."
                    )
            else:
                flash("Invalid password.")
        else:
            flash("User does not exist.")

        return redirect(url_for("login"))
    return render_template("login.html")


def send_confirmation_email(user_email, token):
    msg = Message(
        "Potwierdź rejestrację",
        sender="your_email@example.com",
        recipients=[user_email],
    )
    msg.body = f"Click on the link below to confirm your registration: http://127.0.0.1:5000/confirm/{token}"  # localhost

    mail.send(msg)


@app.route("/confirm/<token>")
def confirm_email(token):
    user = User.verify_confirmation_token(token)
    if user is None:
        flash("The confirmation link is invalid or has expired.", "danger")
        return redirect(url_for("login"))
    if user.confirmed:
        flash("Account already confirmed. Please login.", "success")
    else:
        user.confirmed = True
        db.session.commit()
        return render_template("confirmed.html")


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route("/dashboard")
@login_required
def dashboard():
    users = User.query.all()
    return render_template("dashboard.html", users=users)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("login"))


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        user = User.query.filter_by(email=email).first()
        if user:
            token = user.get_confirmation_token()
            send_reset_password_email(user.email, token)
            flash("Check your email for instructions to reset your password.")
            return redirect(url_for("login"))
        else:
            flash("Email not registered in our system.")
    return render_template("forgot_password.html")


def send_reset_password_email(user_email, token):
    msg = Message(
        "Reset Password",
        sender="your_email@example.com",
        recipients=[user_email],
    )
    msg.body = f"Click the following link to reset your password: http://127.0.0.1:5000/reset_password/{token}"  # localhost
    mail.send(msg)


@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.verify_confirmation_token(token)
    if user is None:
        flash("The reset link is invalid or has expired.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        errors = []

        if password != confirm_password:
            errors.append("Passwords do not match.")

        if user.check_password(password):
            errors.append(
                "The new password cannot be the same as the current password."
            )

        password_pattern = re.compile(
            r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])[A-Za-z\d@$!%*?&#]{8,}$"
        )

        if not password_pattern.match(password):
            errors.append(
                "Password must be at least 8 characters, contain an uppercase letter, a lowercase letter, a number, and a special character."
            )

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("reset_password.html", token=token)
        else:
            user.set_password(password)
            db.session.commit()
            flash("Your password has been updated!", "success")
            return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/change_password_request", methods=["GET", "POST"])
@login_required
def change_password_request():
    if request.method == "POST":
        current_password = request.form["current_password"]
        if current_user.check_password(current_password):
            token = current_user.get_confirmation_token()
            send_reset_password_email(current_user.email, token)
            flash("Check your email for instructions to reset your password.")
            return redirect(url_for("dashboard"))
        else:
            flash("Incorrect current password.")
    return render_template("change_password_request.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
