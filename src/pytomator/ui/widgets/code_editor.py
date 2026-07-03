from dataclasses import dataclass

from PyQt6.Qsci import QsciScintilla, QsciLexerPython
from PyQt6.QtGui import QColor, QFont, QPalette


@dataclass(frozen=True)
class _EditorTheme:
    background: str
    foreground: str
    margin_background: str
    margin_foreground: str
    selection_background: str
    selection_foreground: str
    caret_line: str
    execution: str
    execution_highlight: tuple[int, int, int, int]
    comment: str
    keyword: str
    string: str
    number: str
    class_name: str
    function_name: str
    operator: str


_LIGHT_THEME = _EditorTheme(
    background="#FFFFFF",
    foreground="#202124",
    margin_background="#F1F3F4",
    margin_foreground="#697078",
    selection_background="#B8D7F8",
    selection_foreground="#111111",
    caret_line="#F3F6F8",
    execution="#258A38",
    execution_highlight=(37, 138, 56, 38),
    comment="#5F7F5A",
    keyword="#7A3E9D",
    string="#A33A2B",
    number="#1C6E8C",
    class_name="#845400",
    function_name="#005A9C",
    operator="#444444",
)

_DARK_THEME = _EditorTheme(
    background="#1E1F22",
    foreground="#D8DEE9",
    margin_background="#18191C",
    margin_foreground="#858B94",
    selection_background="#365A7A",
    selection_foreground="#FFFFFF",
    caret_line="#282A2E",
    execution="#58C66D",
    execution_highlight=(88, 198, 109, 42),
    comment="#8FAF87",
    keyword="#C792EA",
    string="#ECC48D",
    number="#82AAFF",
    class_name="#FFCB6B",
    function_name="#82AAFF",
    operator="#C5CAD3",
)


class CodeEditor(QsciScintilla):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Fonte
        font = QFont("JetBrains Mono", 11)
        self.setFont(font)
        self.setMarginsFont(font)

        # Números de linha
        self.setMarginType(0, QsciScintilla.MarginType.NumberMargin)
        self.setMarginWidth(0, "00000")

        # Lexer Python
        lexer = QsciLexerPython(self)
        lexer.setFont(font)
        self.setLexer(lexer)

        # Aparência
        self.setCaretLineVisible(True)
        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        # Tabs
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setAutoIndent(True)
        
        # Marcador de execução
        self.EXECUTION_MARKER = 1
        self.markerDefine(QsciScintilla.MarkerSymbol.RightArrow, self.EXECUTION_MARKER)

        self.EXECUTION_INDICATOR = 0
        self.indicatorDefine(QsciScintilla.IndicatorStyle.FullBoxIndicator, self.EXECUTION_INDICATOR)
        self.setIndicatorDrawUnder(True)

        self._apply_theme(lexer, self._theme_for_palette(self.palette()))

    @staticmethod
    def _theme_for_palette(palette: QPalette) -> _EditorTheme:
        """Choose a theme from the effective Qt window palette."""
        return (
            _DARK_THEME
            if palette.color(QPalette.ColorRole.Window).lightness() < 128
            else _LIGHT_THEME
        )

    def _apply_theme(self, lexer: QsciLexerPython, theme: _EditorTheme) -> None:
        background = QColor(theme.background)
        foreground = QColor(theme.foreground)

        self.setPaper(background)
        self.setColor(foreground)
        self.setMarginsBackgroundColor(QColor(theme.margin_background))
        self.setMarginsForegroundColor(QColor(theme.margin_foreground))
        self.setSelectionBackgroundColor(QColor(theme.selection_background))
        self.setSelectionForegroundColor(QColor(theme.selection_foreground))
        self.setCaretForegroundColor(foreground)
        self.setCaretLineBackgroundColor(QColor(theme.caret_line))

        lexer.setDefaultPaper(background)
        lexer.setDefaultColor(foreground)
        for style in range(128):
            lexer.setPaper(background, style)

        syntax_colors = {
            QsciLexerPython.Comment: theme.comment,
            QsciLexerPython.CommentBlock: theme.comment,
            QsciLexerPython.Keyword: theme.keyword,
            QsciLexerPython.SingleQuotedString: theme.string,
            QsciLexerPython.DoubleQuotedString: theme.string,
            QsciLexerPython.TripleSingleQuotedString: theme.string,
            QsciLexerPython.TripleDoubleQuotedString: theme.string,
            QsciLexerPython.Number: theme.number,
            QsciLexerPython.ClassName: theme.class_name,
            QsciLexerPython.FunctionMethodName: theme.function_name,
            QsciLexerPython.Operator: theme.operator,
        }
        for style, color in syntax_colors.items():
            lexer.setColor(QColor(color), style)

        execution_color = QColor(theme.execution)
        self.setMarkerBackgroundColor(execution_color, self.EXECUTION_MARKER)
        self.setMarkerForegroundColor(execution_color, self.EXECUTION_MARKER)
        self.setIndicatorForegroundColor(
            QColor(*theme.execution_highlight), self.EXECUTION_INDICATOR
        )

    def get_code(self) -> str:
        return self.text()

    def highlight_line(self, lineno: int):
        self.clearExecutionMarker()
        self.setExecutionMarker(lineno - 1)
        self.ensureLineVisible(lineno - 1)

    def clearExecutionMarker(self):
        self.markerDeleteAll(self.EXECUTION_MARKER)
        self.clearIndicatorRange(0, 0, self.lines(), 0, self.EXECUTION_INDICATOR)

    def setExecutionMarker(self, line: int):
        self.markerAdd(line, self.EXECUTION_MARKER)
        self.fillIndicatorRange(line, 0, line, len(self.text(line)), self.EXECUTION_INDICATOR)
    
