from pydantic import BaseModel, ConfigDict, Field


class Viewer(BaseModel):
    """Who is reading. A source is visible when its allowed principals and `principals` meet.

    `"public"` is an ordinary principal: a viewer sees public sources only if it names it. A viewer
    without principals sees nothing.

    Examples:
        >>> Viewer(principals=frozenset({"public", "team-a"}))
    """

    model_config = ConfigDict(frozen=True)

    principals: frozenset[str] = Field(description="The principals the reader acts as.")
