import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
# app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    get_portfolio = db.execute("SELECT symbol, name, shares, price FROM stocks WHERE user_id=:user_id",
    user_id=session["user_id"])

    balance = []
    # Loop through portfolio for share values
    for record in get_portfolio:
        symbol = record['symbol']
        name = record['name']
        shares = record['shares']
        share = lookup(record['symbol'])
        price = share['price']
        share_total = shares * price
        # Push balance to list
        balance.append(share_total)


    # Get user's cash balance from users table
    rows = db.execute("SELECT cash, username FROM users WHERE id=:user_id", user_id=session["user_id"])
    cash_amount = rows[0]["cash"]

    # Total stocks in balance list
    sum_total = sum(balance)

    # Total stocks plus cash
    portfolio_total = cash_amount + sum_total

    # Get username
    username=rows[0]["username"]

    # User has not purchased any stocks, display index page with total cash balance
    if not get_portfolio or not portfolio_total:
        flash(f"You haven't purchased any shares, yet, {username}.")
        return render_template("index.html", get_portfolio=get_portfolio, cash_amount=cash_amount, portfolio_total=portfolio_total, username=username)

    return redirect("/")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # Get values for the stock symbol and shares fields
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        # Lookup stock symbols
        quote = lookup(symbol)

        # Check for null or 0 values and return apology
        if not quote:
            return apology("invalid symbol")

        if not shares:
           return apology("must enter an amount of shares you wish to purchase")

        if int(shares) < 0:
            return apology("must enter shares above 0")

        # Get user's cash balance from users table
        rows = db.execute("SELECT cash, username FROM users WHERE id=:user_id", user_id=session["user_id"])
        user_cash = rows[0]["cash"]
        username = rows[0]["username"]

        # Share price times amount of shares purchased
        price = quote["price"]
        total_price = price * int(shares)

        # If the user's balance is less than the total_price, return an error
        if user_cash < total_price:
            return apology("not enough cash to buy these shares.")

        # Transaction type
        transaction = "BOUGHT"

        db.execute("INSERT INTO transactions (user_id, exchange, symbol, name, shares, price) VALUES (:user_id, :exchange, :symbol, :name, :shares, :price)",
                    user_id = session["user_id"],
                    exchange = transaction,
                    symbol = quote["symbol"],
                    name = quote["name"],
                    shares = shares,
                    price = price)

        current_cash = user_cash - total_price

        db.execute("UPDATE users SET cash=:cash WHERE id=:user_id",
                    user_id=session["user_id"],
                    cash=current_cash)

        # Add to stocks table
        portfolio = db.execute("SELECT shares FROM stocks WHERE user_id=:user_id AND symbol=:symbol",
                                user_id=session["user_id"],
                                symbol=symbol)

        # If symbol exists
        if len(portfolio) == 1:

            total_shares = portfolio[0]["shares"] + int(shares)

            db.execute("UPDATE stocks SET name=:name, shares=:shares, price=:price WHERE user_id=:user_id AND symbol=:symbol",
                        name=quote["name"],
                        shares=total_shares,
                        price=quote["price"],
                        user_id=session["user_id"],
                        symbol=symbol)

        else:
            db.execute("INSERT INTO stocks (user_id, symbol, name, shares, price) VALUES(:user_id, :symbol, :name, :shares, :price)",
                                            user_id=session["user_id"],
                                            symbol=symbol,
                                            name=quote["name"],
                                            shares=shares,
                                            price=quote["price"])

        # Query database for user's stocks, ADD EXCHANGE, PRICE AND TOTAL TO PORTFOLIOS
        total_stocks = db.execute("SELECT symbol, name, shares, price FROM stocks WHERE user_id=:user_id ORDER BY symbol DESC",
                                    user_id=session["user_id"])

        balance = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
        cash_amount = balance[0]["cash"]

        get_portfolio = db.execute("SELECT symbol, name, shares, price FROM stocks WHERE user_id=:user_id", user_id=session["user_id"])

        # List to capture the balance of all purchased stocks at the current stock price
        balance = []
        # Capture each stock's attributes for the logged in user
        for record in get_portfolio:
            symbol = record["symbol"]
            name = record["name"]
            shares = record["shares"]
            share = lookup(record["symbol"])
            price = share["price"]
            share_total = shares * price
            balance.append(share_total)

        # Total stocks in balance list
        sum_total = sum(balance)
        # Total stocks plus cash
        portfolio_total = cash_amount + sum_total

        flash(f"You just purchased {shares} shares of {symbol}.")
        return render_template("index.html", get_portfolio=get_portfolio, cash_amount=cash_amount, portfolio_total=portfolio_total, username=username)

    # GET request
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    trades = db.execute("SELECT * FROM transactions WHERE user_id=:user_id", user_id=session["user_id"])

    for trade in trades:
        date = trade["date"]
        exchange = trade["exchange"]
        symbol = trade["symbol"]
        name = trade["name"]
        shares = trade["shares"]
        price = trade["price"]

    return render_template("history.html", trades=trades)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password")

        username = rows[0]["username"]

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        flash(f"Welcome back, {username}!")
        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST
    if request.method == "POST":

        symbol = request.form.get("symbol")
        quote = lookup(symbol)

        if not symbol:
            return apology("must enter a symbol")

        if quote == None:
            return apology("invalid symbol")

        return render_template("quoted.html", quote=quote)

    # GET request
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Log current user out prior to registering
    session.clear()

    # User reached route via POST
    if request.method == "POST":

        # Require username when registering
        name = request.form.get("username")
        # Check is username exists
        check_username = db.execute("SELECT * FROM users WHERE username=(:username)", username=name)
        # Hash password
        password = request.form.get("password")
        password_hash = generate_password_hash(password)
        # Password confirmation
        confirmation = request.form.get("password_confirmation")

        if not name:
            return apology("must provide username to register.")

        # Check if username already exists
        elif check_username:
            return apology("that username already exists.")

        # Require password when registering
        elif not password:
            return apology("must provide password to register.")

        elif not confirmation:
            return apology("must provide a password confirmation value.")

        # Require a password confirmation and make sure the field is not empty and that passwords match
        elif confirmation != password:
            return apology("your passwords do not match.")

        # INSERT the new user into users, storing a hash of the user’s password
        add_user = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                                username=name,
                                hash=password_hash)

        # Remember user session
        session["user_id"] = add_user
        print(session["user_id"])

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "GET":

        symbols = db.execute("SELECT symbol from stocks WHERE user_id=:user_id", user_id=session["user_id"])

        # Build a list of the user's current stock symbols for the dropdown list in sell
        symbol_list = []
        for record in symbols:
            symbol = record["symbol"]
            symbol_list.append(symbol)

        return render_template("sell.html", symbol_list=symbol_list)

    # POST request to sell shares
    else:
        # Get values for the stock symbol and shares fields
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        # Lookup stock symbols
        quote = lookup(symbol)
        price = quote["price"]

        # Throw error if user does not enter an amount of shares
        if not shares:
          return apology("must enter an amount of shares you wish to purchase")

        # Check for 0 or negative values
        if int(shares) < 0:
            return apology("must enter shares above 0")

        # Get user's cash balance from users table
        rows = db.execute("SELECT cash, username FROM users WHERE id=:user_id", user_id=session["user_id"])
        user_cash = rows[0]["cash"]
        username = rows[0]["username"]

        # Get user's total of stock shares for the symbol selected in the dropdown
        stocks = db.execute("SELECT symbol, shares FROM stocks WHERE user_id=:user_id AND symbol=:symbol",
                            user_id=session["user_id"],
                            symbol=symbol)

        total_shares = stocks[0]["shares"]

        # Share price times amount of shares sold
        total_price = price * int(shares)

        # If the user's amount of shares is less than selected, return an error
        if total_shares < int(shares):
            return apology(f"You don't have {shares} shares of {symbol} to sell.")

        # # Transaction type
        transaction = "SOLD"

        db.execute("INSERT INTO transactions (user_id, exchange, symbol, name, shares, price) VALUES (:user_id, :exchange, :symbol, :name, :shares, :price)",
                    user_id = session["user_id"],
                    exchange = transaction,
                    symbol = quote["symbol"],
                    name = quote["name"],
                    shares = shares,
                    price = price)

        current_cash = user_cash + total_price

        db.execute("UPDATE users SET cash=:cash WHERE id=:user_id",
                    user_id=session["user_id"],
                    cash=current_cash)

        # # Subtracts shares sold from stocks table
        portfolio = db.execute("SELECT shares FROM stocks WHERE user_id=:user_id AND symbol=:symbol",
                                user_id=session["user_id"],
                                symbol=symbol)


        # If symbol exists
        if len(portfolio) == 1:

            total_shares = portfolio[0]["shares"] - int(shares)

            db.execute("UPDATE stocks SET name=:name, shares=:shares, price=:price WHERE user_id=:user_id AND symbol=:symbol",
                        name=quote["name"],
                        shares=total_shares,
                        price=quote["price"],
                        user_id=session["user_id"],
                        symbol=symbol)

        else:
            db.execute("INSERT INTO stocks (user_id, symbol, name, shares, price) VALUES(:user_id, :symbol, :name, :shares, :price)",
                                            user_id=session["user_id"],
                                            symbol=symbol,
                                            name=quote["name"],
                                            shares=shares,
                                            price=quote["price"])

        # Query database for user's stocks, ADD EXCHANGE, PRICE AND TOTAL TO PORTFOLIOS
        total_stocks = db.execute("SELECT symbol, name, shares, price FROM stocks WHERE user_id=:user_id ORDER BY symbol DESC",
                                    user_id=session["user_id"])

        balance = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
        cash_amount = balance[0]["cash"]

        get_portfolio = db.execute("SELECT symbol, name, shares, price FROM stocks WHERE user_id=:user_id", user_id=session["user_id"])

        # List to capture the balance of all purchased stocks at the current stock price
        balance = []
        # Capture each stock's attributes for the logged in user
        for record in get_portfolio:
            symbol = record["symbol"]
            name = record["name"]
            shares = record["shares"]

            share = lookup(record["symbol"])
            price = share["price"]
            share_total = shares * price
            balance.append(share_total)

        # Total stocks in balance list
        sum_total = sum(balance)
        # Total stocks plus cash
        portfolio_total = cash_amount + sum_total

        if total_shares == 0:
            for stock in stocks:
                # Delete records with 0 share values
                db.execute("DELETE FROM stocks WHERE shares=?", 0)

        flash(f"You just sold {shares} shares of {symbol}.")
        return render_template("index.html", get_portfolio=get_portfolio, cash_amount=cash_amount, portfolio_total=portfolio_total, username=username)

@app.route("/transfer", methods=["GET", "POST"])
@login_required
def transfer():
    """Sell shares of stock"""
    if request.method == "GET":

        return render_template("transfer.html")

    else:

        bank = request.form.get("bank")

        users = db.execute("SELECT cash FROM users WHERE id=:user_id", user_id=session["user_id"])
        balance = users[0]["cash"]
        cash_total = balance + int(bank)

        if not bank:
            return apology("must enter a dollar amount in order to transfer money.")

        db.execute("UPDATE users SET cash=:cash WHERE id=:user_id",
                    cash=cash_total,
                    user_id=session["user_id"])

        flash(f"You added ${bank} to your balance")
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
