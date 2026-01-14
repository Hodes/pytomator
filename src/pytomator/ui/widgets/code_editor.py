from PyQt6.Qsci import QsciScintilla, QsciLexerPython
from PyQt6.QtGui import QFont, QColor


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
        lexer = QsciLexerPython()
        lexer.setFont(font)
        self.setLexer(lexer)

        # Aparência
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(QColor("#92e6ff55"))

        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        # Tabs
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setAutoIndent(True)
        
        # Marcador de execução
        self.EXECUTION_MARKER = 1
        self.markerDefine(QsciScintilla.MarkerSymbol.RightArrow, self.EXECUTION_MARKER)
        self.setMarkerBackgroundColor(QColor("#44CA29"), self.EXECUTION_MARKER)
        
        self.EXECUTION_INDICATOR = 0
        self.indicatorDefine(QsciScintilla.IndicatorStyle.FullBoxIndicator, self.EXECUTION_INDICATOR)
        self.setIndicatorForegroundColor(QColor(0, 120, 215, 60), self.EXECUTION_INDICATOR)
        self.setIndicatorDrawUnder(True)

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
    