# shared/types.py
from sqlalchemy.types import UserDefinedType

class Vector(UserDefinedType):
    def get_col_spec(self, **kw):
        return f"vector({self.dim})"

    def __init__(self, dim):
        self.dim = dim

    def bind_processor(self, dialect):
        def process(value):
            return value
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            return value
        return process