from flask import Flask, request, make_response, render_template, redirect
import sqlite3
import secrets
import hashlib
import re

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

def createSessionAuthenticated(userName):
	h = hashlib.sha512()
	h.update(str.encode(userName))
	sid = h.hexdigest()

	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("INSERT OR REPLACE INTO sessions VALUES (:sid, (SELECT datetime('now','+1 hour')), :userName);", {"sid": sid, "userName": userName})
	db.commit()
	db.close()

	return (sid, 3600)

def removeSession(sessionID):
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("DELETE FROM sessions WHERE sessionID = :sid;", {"sid": sessionID})
	db.commit()
	db.close()

	return ("", 0)

def removeSessionsExpired():
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("DELETE FROM sessions WHERE expiresAfter < (SELECT datetime('now'));")
	db.commit()
	db.close()

def createUser(userName, password):
	salt = secrets.token_hex(32)

	h = hashlib.sha512()
	h.update(str.encode(salt))
	h.update(str.encode(password))
	hash = h.hexdigest()

	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	try:
		c.execute("INSERT INTO users VALUES (:userName, :salt, :hash);", {"userName": userName, "salt": salt, "hash": hash})
	except sqlite3.IntegrityError: # username already exists
		db.close()
		return False

	db.commit()
	db.close()
	return True

def getSession(request):
	sessionCookie = request.cookies.get("session")
	if sessionCookie == None:
		return None

	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT sessionID, expiresAfter, userName FROM sessions WHERE sessionID = :sid;", {"sid": sessionCookie})
	session = c.fetchone()
	db.close()

	return session

def auth(userName, password):
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT salt, hash FROM users WHERE userName = :userName;", {"userName": userName})
	r = c.fetchone()
	db.close()

	if r == None:
		return False # unknown user name

	h = hashlib.sha512()
	h.update(str.encode(r[0])) # salt
	h.update(str.encode(password))
	hash = h.hexdigest()

	return r[1] == hash

def login(userName, password):
	if auth(userName, password):
		return createSessionAuthenticated(userName)
	return None

def vote(user, voteID, votedYes):
	if getPoll(voteID) == None:
		return False

	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	try:
		c.execute("INSERT INTO votes VALUES (:pollID, :userName, :votedYes);", {"pollID": voteID, "userName": user, "votedYes": votedYes})
	except sqlite3.IntegrityError: # already voted
		db.close()
		return False
	db.commit()
	db.close()

	return True

def getPoll(pollID):
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT pollID, title, description, creator, creatorsNotes FROM polls WHERE pollID = :id;", {"id": pollID})
	poll = c.fetchone()
	db.close()

	return poll

def createPoll(user, title, description, notes):
	# get ID for new poll
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT count(*) + 1 FROM polls;")
	pollID = c.fetchone()[0]

	# create poll
	c.execute("INSERT INTO polls VALUES (:id, :title, :description, :creator, :creatorsNotes, (SELECT datetime('now')) );",
			{"id": pollID, "title": title, "description": description, "creator": user, "creatorsNotes": notes})
	db.commit()
	db.close()

	# return pollID
	return pollID

def getVotes(pollID):
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT count(*) FROM votes WHERE pollID = :id AND votedYes = :yes;", {"id": pollID, "yes": True})
	votesYes = c.fetchone()
	c.execute("SELECT count(*) FROM votes WHERE pollID = :id AND votedYes = 0;", {"id": pollID})
	votesNo = c.fetchone()
	db.close()

	return (votesYes[0], votesNo[0])

def votedYes(pollID, username):
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT votedYes FROM votes WHERE pollID = :id AND userName = :username;", {"id": pollID, "username": username})
	userVotedYes = c.fetchone()
	db.close()

	if userVotedYes is None:
		return None

	return userVotedYes[0]

def initDB():
	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("CREATE TABLE IF NOT EXISTS sessions (sessionID TEXT NOT NULL UNIQUE, expiresAfter TEXT NOT NULL, userName TEXT NOT NULL, PRIMARY KEY(sessionID));")
	c.execute("CREATE TABLE IF NOT EXISTS users (userName TEXT NOT NULL UNIQUE, salt TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(userName));")
	c.execute("CREATE TABLE IF NOT EXISTS polls (pollID INTEGER NOT NULL UNIQUE, title TEXT NOT NULL, description TEXT NOT NULL, \
			creator TEXT NOT NULL, creatorsNotes TEXT, creationDate TEXT NOT NULL, PRIMARY KEY(pollID));")
	c.execute("CREATE TABLE IF NOT EXISTS votes (pollID INTEGER NOT NULL, userName TEXT NOT NULL, votedYes INTEGER NOT NULL, PRIMARY KEY(pollID, userName));")
	db.commit()
	db.close()

def validUserName(userName):
	# a valid user name may contain only alphanumeric characters
	# and must be at least 4 and at most 32 characters long
	return not re.match(r"^[a-zA-Z0-9]{4,32}$", userName) == None

def validPassword(password):
	# a valid password may contain only alphanumeric characters or underscores
	# and must be at least 4 and at most 32 characters long
	return not re.match(r"^[a-zA-Z0-9_]{4,32}$", password) == None

def validVoteID(voteID):
	# a valid voteID may contain only numeric characters
	# and must be at least 1 character long
	# and must be greater as zero
	if re.match(r"^[0-9]+$", voteID) == None:
		return False
	return int(voteID) > 0

def validVoteType(voteType):
	return voteType == "Yes" or voteType == "No"

def validPollTitle(title):
	# a valid poll title may contain only alphanumeric characters or spaces
	# and must be at least 4 and at most 48 characters long
	# and must not start with a space, lower case letter or number
	# and must not end with a space
	return not re.match(r"^[A-Z][a-zA-Z0-9 ]{2,46}[a-zA-Z0-9]$", title) == None

def validPollDescription(description):
	# a valid poll description may contain any characters except a newline
	# and must be at least 4 and at most 256 characters long
	# and must start with a upper case letter
	# and must not end with whitespace
	return not re.match(r"^[A-Z].{2,254}\S$", description) == None

def validPollPrivateNotes(notes):
	# a valid poll private note may contain any characters except a newline
	# and must be at most 64 characters long
	return not re.match(r"^.{,64}$", notes) == None

@app.route("/index.html")
def pageIndex():
	session = getSession(request)

	db = sqlite3.connect("data.sqlite3")
	c = db.cursor()
	c.execute("SELECT polls.pollID, title, sum(votedYes), count(votedYes) FROM polls \
		LEFT JOIN votes ON polls.pollID == votes.pollID \
		GROUP BY polls.pollID \
		ORDER BY polls.pollID DESC;") # sum(votesYes) is None, if count(votedYes) is 0
	polls = c.fetchall() # [(pollID_66, pollTitle_66, votesYes, votesTotal), (pollID_65, pollTitle_65, votesYes, votesTotal), ...]

	if session != None:
		c.execute("SELECT pollID, votedYes FROM votes WHERE userName = :userName;", {"userName": session[2]})
		userVotedYes = dict(c.fetchall()) # {pollID_1: 1, pollID_4: 0, ...}
	else:
		userVotedYes = {}

	db.close()

	return render_template("index.html", session = session, polls = polls, votedYes = userVotedYes)

@app.route("/login.html", methods=['GET', 'POST'])
def pageLogin():
	# redirect if user is already logged in
	if not getSession(request) == None:
		return redirect("index.html")

	if request.method == "POST":
		try:
			userProvided = request.form["user"]
			passwordProvided = request.form["password"]
		except KeyError:
			abort(400)

		if not validUserName(userProvided) or not validPassword(passwordProvided):
			return render_template("login.html", msg = "Wrong username / password", current = "login")

		result = login(userProvided, passwordProvided)
		if result == None:
			return render_template("login.html", msg = "Wrong username / password", user = userProvided, current = "login")

		# redirect on successful login
		response = redirect("index.html")
		response.set_cookie(key = "session", value = result[0],
				max_age = result[1]);
		return response
	else:
		return render_template("login.html", current = "login")

@app.route("/logout.html", methods=['POST'])
def pageLogout():
	session = getSession(request)

	# redirect if user is not logged in
	if session == None:
		return redirect("index.html")

	result = removeSession(session[0])

	# redirect on successful logout
	response = redirect("index.html")
	response.set_cookie(key = "session", value = result[0],
			max_age = result[1]);
	return response

@app.route("/register.html", methods=['GET', 'POST'])
def pageRegister():
	# redirect if user is already logged in
	if not getSession(request) == None:
		return redirect("index.html")

	if request.method == "POST":
		try:
			userProvided = request.form["user"]
			passwordProvided = request.form["password"]
		except KeyError:
			abort(400)

		if not validUserName(userProvided) or not validPassword(passwordProvided):
			return render_template("register.html", msg = "Illegal input", current = "reg")

		if not createUser(userProvided, passwordProvided):
			return render_template("register.html", msg = "Username already exists", user = userProvided, current = "reg")

		# login once user is created
		result = login(userProvided, passwordProvided)

		response = redirect("index.html")
		response.set_cookie(key = "session", value = result[0],
				max_age = result[1]);
		return response
	else:
		return render_template("register.html", current = "reg")

@app.route("/vote.html", methods=['GET', 'POST'])
def pageVote():
	session = getSession(request)
	
	if request.method == "POST":
		# redirect if user is not logged in
		if session == None:
			return redirect("login.html")

		try:
			voteIDProvided = request.args["v"]
			voteTypeProvided = request.form["vote"]
		except KeyError:
			abort(400)

		if not validVoteID(voteIDProvided) or not validVoteType(voteTypeProvided):
			return render_template("vote.html", msg = "Illegal input", session = session)

		success = vote(session[2], voteIDProvided, voteTypeProvided == "Yes")

		if success == False:
			return render_template("vote.html", msg = "Vote failed. Already participated, vote ended or not found.", session = session)

		return redirect("vote.html?v={}".format(voteIDProvided))
	else:
		try:
			voteIDProvided = request.args["v"]
		except KeyError:
			return redirect("index.html")

		if not validVoteID(voteIDProvided):
			return render_template("vote.html", msg = "Vote not found.", session = session)

		pollInfo = getPoll(voteIDProvided)

		if pollInfo is None:
			return render_template("vote.html", msg = "Vote not found.", session = session)

		(votesYes, votesNo) = getVotes(voteIDProvided)

		if session != None:
			userVotedYes = votedYes(voteIDProvided, session[2])
		else:
			userVotedYes = None

		return render_template("vote.html", session = session, pollID = pollInfo[0],
				pollTitle = pollInfo[1], pollDescription = pollInfo[2],
				pollCreator = pollInfo[3], pollCreatorsNotes = pollInfo[4],
				votesYes = votesYes, votesNo = votesNo, votedYes = userVotedYes)

@app.route("/create.html", methods=['GET', 'POST'])
def pageCreate():
	session = getSession(request)

	# redirect if user is not logged in
	if session == None:
		return redirect("login.html")

	if request.method == "POST":
		try:
			titleProvided = request.form["title"]
			descriptionProvided = request.form["description"]
			notesProvided = request.form["notes"]
		except KeyError:
			abort(400)

		if not validPollTitle(titleProvided) or not validPollDescription(descriptionProvided) or not validPollPrivateNotes(notesProvided):
			return render_template("create.html", session = session, current = "create",
					title = titleProvided, description = descriptionProvided, notes = notesProvided, msg = "Illegal input.")

		result = createPoll(session[2], titleProvided, descriptionProvided, notesProvided)

		if result == None:
			return render_template("create.html", session = session, current = "create",
					title = titleProvided, description = descriptionProvided, notes = notesProvided, msg = "Creation failed.")

		return redirect("vote.html?v={}".format(result))
	else:
		return render_template("create.html", session = session, current = "create")

initDB()
