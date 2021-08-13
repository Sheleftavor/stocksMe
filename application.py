import os, re
from datetime import timedelta
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=5)
    
    
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
app.config["SESSION_FILE_DIR"] = mkdtemp()
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
    stocks = db.execute("SELECT stocks_name FROM stocks WHERE users_id=?", session["user_id"])[0]
    nums = db.execute("SELECT stocks_num FROM stocks WHERE users_id=?", session["user_id"])[0]
    symbols = []

    symbols = stocks['stocks_name'].split(", ")
    nums = nums['stocks_num'].split(", ")
    
    prices = []
    total = []
    totalUsd = []
    stocks_names = []
    if symbols[0] != '': 
        for i, symbol in enumerate(symbols):
            price = lookup(symbol)["price"]
            priceUsd = usd(float(price))
            prices.append(priceUsd)
            total.append(float(price) * float(nums[i]))
            totalUsd.append(usd(float(price) * float(nums[i])))
            stocks_names.append(lookup(symbol)["name"])
     
        
    intcash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
    cash = usd(float(intcash))
    
    totalCash = (float(intcash) + sum(float(t) for t in total))
    totalCash = usd(float(totalCash))
    
    if nums != ['']:
        nums = [int(float(t)) for t in nums]

    return render_template("index.html", cash=cash, symbols=symbols, nums=nums, prices=prices, total=totalUsd, length=len(symbols), names=stocks_names, totalCash=totalCash)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    
    if request.method == "POST":
        symbol = request.form.get("Symbol").upper()
        shares = request.form.get("Shares")
        
        if lookup(symbol) is None:
            flash("Invalid Stock Name.")
            return render_template("buy.html")
            
            
        total = float(float(shares) * lookup(symbol)["price"])
        

        stocks = db.execute("SELECT stocks_name FROM stocks WHERE users_id=?", session["user_id"])
        nums = db.execute("SELECT stocks_num FROM stocks WHERE users_id=?", session["user_id"])
        stocks = stocks[0]["stocks_name"]
        nums = nums[0]["stocks_num"]
        
        if stocks != '':
            stocks = stocks.split(", ")
            nums = nums.split(", ")
            
            isIn = False  
            for i, stock in enumerate(stocks):
                if stock == symbol:
                    isIn = True
                    nums[i] = str(float(nums[i]) + int(shares))
        
            if not isIn:
                stocks = ", ".join(stocks) +  ", " + symbol
                nums  = ", ".join(nums) + ", " + shares
            
            else:
                stocks = ", ".join(stocks)
                nums  = ", ".join(nums)
            
        else:
            stocks = symbol
            nums = str(shares)
        
        print(stocks, nums)
        
        db.execute("UPDATE stocks SET stocks_name = ?, stocks_num = ? WHERE users_id=?", stocks, nums, session["user_id"])
        
        """Update Cash"""
        cash = float(db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]["cash"]) - total
        db.execute("UPDATE users SET cash = ? WHERE id=?", cash, session["user_id"])
        
        """Update History"""
        stocksH = db.execute("SELECT stocks_name FROM history WHERE users_id = ?", session["user_id"])[0]["stocks_name"]
        sharesH = db.execute("SELECT shares FROM history WHERE users_id = ?", session["user_id"])[0]["shares"]
        priceH = db.execute("SELECT price FROM history WHERE users_id = ?", session["user_id"])[0]["price"]
        
        if stocksH != "":
            priceH = priceH + ", " + str(lookup(symbol)["price"])
            stocksH = stocksH + ", " + symbol
            sharesH = sharesH + ", " + str(shares)
        
        else:
            stocksH = symbol
            sharesH = str(shares)
            priceH = lookup(symbol)["price"]
        
        db.execute("UPDATE history SET stocks_name = ?, shares = ?, price = ?", stocksH, sharesH, priceH)
        
        """Show Massege"""
        if float(shares) > 1:
            massege = shares + " Shares Of " + symbol + " Has Been Bought!"
        else:
            massege ="A Shares Of " + symbol + " Has Been Bought!"
        
        flash(massege)
        
        return redirect("/")
        
    elif request.method == "GET":
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    
    i = db.execute("SELECT stocks_name, shares, price FROM history WHERE users_id = ?", session["user_id"])[0]
    stocks = i["stocks_name"].split(", ")
    tmpS = i["shares"].split(", ")
    prices = i["price"].split(", ")
    
    totals = []
    shares = []
    oper = []
    for i, t in enumerate(prices):
        totals.append(float(t) * int(tmpS[i]) * -1)
        shares.append(abs(int(tmpS[i])))
        
        if int(tmpS[i]) > 0:
            oper.append("Buy")
        else:
            oper.append("Sell")
        
    names = []
    for s in stocks:
        names.append(lookup(s)["name"])
    
    
    """Reverse Table"""
    oper.reverse()
    stocks.reverse()
    shares.reverse()
    prices.reverse()
    totals.reverse()
    names.reverse()
    
     
    return render_template("history.html", oper=oper, stocks=stocks, shares=shares, prices=prices, totals=totals, length = len(stocks), names=names)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Username Required.")
            return render_template("login.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Password Required.")
            return render_template("login.html")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            flash("Invalid Username and/or Password.")
            return render_template("login.html")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Logged In!")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()
    flash("Logged Out")
    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    
    if request.method == "POST":
        symbol = request.form.get("stock").upper()
        
        if lookup(symbol) is None:
            flash("Invalid Stock Name.")
            return render_template("quoteS.html")
            
        price = usd(lookup(symbol)["price"])
        stock = lookup(symbol)["name"]
        
        massege = "A share of " + stock + " costs " + price + "."
        
        return render_template("quoteA.html", massege=massege)
        
        
    elif request.method == "GET":
        return render_template("quoteS.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        
        if not request.form.get("username"):
            flash("Username Required")
            return redirect("/register")
            
        username = request.form.get("username")
        print(username)
        password_hash = generate_password_hash(request.form.get("password"))
        
        for user in db.execute("SELECT username FROM users"):
            if user['username'] == username:
                return apology("User Already Registered")
         
               
        already = db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, password_hash)
        db.execute("INSERT INTO stocks (users_id, stocks_name, stocks_num) VALUES(?, ?, ?)",already, "", "")
        db.execute("INSERT INTO history (users_id, stocks_name, shares, price) VALUES(?, ?, ?, ?)",already, "", "", "")
        session["user_id"] = already
        
        flash("Registered")
        
        return redirect("/")
        
        
    
    elif request.method == "GET":
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    
    if request.method == "POST":
        stocks = db.execute("SELECT stocks_name FROM stocks WHERE users_id=?", session["user_id"])[0]["stocks_name"].split(", ")
        shares = db.execute("SELECT stocks_num FROM stocks WHERE users_id=?", session["user_id"])[0]["stocks_num"].split(", ")
        
        index = -1
        for i in range(0, len(stocks)):
            if stocks[i] == request.form.get("stock"):
                index = i
        
        if index != -1:
            
            if int(float(shares[index])) < int(request.form.get("shares")):
                flash("Tried To Sell More Stocks Then You Have.")
                return redirect("/sell")
                
            if int(float(shares[index])) == int(request.form.get("shares")):
                shares.pop(index)
                stocks.pop(index)
                
            else:
                shares[index] = str(int(float(shares[index])) - int(request.form.get("shares")))
            
        stocks = ", ".join(stocks)
        shares = ", ".join(shares)
        
        db.execute("UPDATE stocks SET stocks_name = ?, stocks_num = ? WHERE users_id = ?", stocks, shares, session["user_id"])
        
        
        """Update Cash"""
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
        total = int(lookup(request.form.get("stock"))["price"]) * int(request.form.get("shares"))
        total += cash 
        print(total)
        db.execute("UPDATE users SET cash = ? WHERE id = ?", total, session["user_id"])
        
        
        """Update History"""
        stocksH = db.execute("SELECT stocks_name FROM history WHERE users_id = ?", session["user_id"])[0]["stocks_name"]
        sharesH = db.execute("SELECT shares FROM history WHERE users_id = ?", session["user_id"])[0]["shares"]
        priceH = db.execute("SELECT price FROM history WHERE users_id = ?", session["user_id"])[0]["price"]
        
        if stocksH != "":
            priceH = priceH + ", " + str(lookup(request.form.get("stock"))["price"])
            stocksH = stocksH + ", " + request.form.get("stock")
            sharesH = sharesH + ", " + str(int(request.form.get("shares")) * -1)
        
        else:
            stocksH = symbol
            sharesH = str(int(request.form.get("shares")) * -1)
            priceH = str(lookup(symbol)["price"])
        
        db.execute("UPDATE history SET stocks_name = ?, shares = ?, price = ?", stocksH, sharesH, priceH)
        
        
        """Display Massege"""
        if int(request.form.get("shares")) > 1:
            massege = request.form.get("shares") + " Shares Of " + request.form.get("stock") + " Has Been Bought!"
        else:
            massege ="A Shares Of " + request.form.get("stock") + " Has Been Sold!"
        
        flash(massege)
        
        
        return redirect("/")
        
        
    elif request.method == "GET":
        stocks = db.execute("SELECT stocks_name FROM stocks WHERE users_id=?", session["user_id"])
        shares = db.execute("SELECT stocks_num FROM stocks WHERE users_id=?", session["user_id"])

        if stocks != []:
            stocks = stocks[0]['stocks_name'].split(", ")
            shares = shares[0]['stocks_num'].split(", ")
        
        else:
            flash("No Stocks To Sell.")
            return render_template("index.html")

        
        return render_template("sell.html", stocks=stocks, shares=shares)
 

@app.route("/settings",  methods=["GET", "POST"])
@login_required
def settings():
    
    if request.method == "POST":

        if 'changeP' in request.form:

            if request.form.get("oldPass") != "":
                newPassHash = generate_password_hash(request.form.get("newPass"))
                db.execute("UPDATE users SET hash = ? WHERE id = ?", newPassHash, session["user_id"])
                
                flash("Password Changed!")
                return redirect("/settings")
                
            else:
                flash("Old Password Required.")
                return redirect("/settings")
        
        
        elif 'addBalanceB' in request.form:
            if request.form.get("addB") != "" and int(request.form.get("addB")) > 0:
                
                cash = float(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]) + float(request.form.get("addB"))
                
                db.execute("UPDATE users SET cash = ? WHERE id = ?", cash, session["user_id"])
                
                
                
                flash("Balance Added!")
                return redirect("/settings")
            
            else:
                flash("Invalid Balance Input.")
                return ("/settings")
           
        
        return redirect("/settings")
    
    elif request.method == "GET":
        balance = usd(db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"])
        return render_template("settings.html", balance=balance)

      
def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
