"""Business operations the routers call: answering, grading, draws, sessions.

A service works on stored rows and raises ApiError for an operation it
refuses. Two modules reach further, because several routers share what they
hold: participants defines the dependencies that identify the student of a
request, and results builds the result bodies of a session.
"""
