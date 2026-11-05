class RetryLater(Exception):
    """Durable scheduling, not an exhausted execution attempt."""
    def __init__(self, when, reason="Cooldown; trailing analysis remains pending"):
        super().__init__(reason)
        self.when = when
