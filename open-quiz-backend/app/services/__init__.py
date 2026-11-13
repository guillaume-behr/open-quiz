"""Business operations the routers call: answering, grading, draws, sessions.

A service raises ApiError for an operation it refuses, but never reads a
request nor builds a response body: that stays in app/routers and
app/responses.
"""
