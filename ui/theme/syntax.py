from pygments.style import Style as PygmentsStyle
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Token,
    Whitespace,
)
from rich.syntax import PygmentsSyntaxTheme

from ui.theme.palette import hex_colour


class PostalStyle(PygmentsStyle):

    background_color = "#191919"

    styles = {
        Token: hex_colour("silver"),
        Whitespace: hex_colour("slate"),
        Comment: f"italic {hex_colour('graphite')}",
        Comment.Preproc: hex_colour("lilac"),

        Keyword: f"bold {hex_colour('violet')}",
        Keyword.Constant: hex_colour("orange"),
        Keyword.Type: hex_colour("teal"),

        Name: hex_colour("silver"),
        Name.Builtin: hex_colour("teal"),
        Name.Class: f"bold {hex_colour('blue')}",
        Name.Decorator: hex_colour("amber"),
        Name.Exception: f"bold {hex_colour('orange')}",
        Name.Function: hex_colour("blue"),
        Name.Namespace: hex_colour("teal"),
        Name.Tag: hex_colour("blue"),
        Name.Variable: hex_colour("silver"),

        String: hex_colour("green"),
        String.Doc: f"italic {hex_colour('graphite')}",
        String.Escape: hex_colour("orange"),
        String.Interpol: hex_colour("amber"),

        Number: hex_colour("amber"),
        Operator: hex_colour("accent"),
        Operator.Word: f"bold {hex_colour('violet')}",
        Punctuation: hex_colour("graphite"),

        Error: f"bold {hex_colour('red')}",

        Generic.Inserted: hex_colour("green"),
        Generic.Deleted: hex_colour("red"),
        Generic.Heading: f"bold {hex_colour('accent')}",
        Generic.Subheading: hex_colour("accent"),
        Generic.Emph: f"italic {hex_colour('silver')}",
        Generic.Strong: f"bold {hex_colour('bright')}",
        Generic.Error: hex_colour("red"),
        Generic.Traceback: hex_colour("red"),
        Generic.Prompt: hex_colour("graphite"),
        Generic.Output: hex_colour("silver"),
    }


POSTAL_SYNTAX = PygmentsSyntaxTheme(PostalStyle)
