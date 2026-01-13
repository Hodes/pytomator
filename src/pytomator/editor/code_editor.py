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
        self.setCaretLineBackgroundColor(QColor("#c2c2c2"))

        self.setBraceMatching(QsciScintilla.BraceMatch.SloppyBraceMatch)

        # Tabs
        self.setIndentationsUseTabs(False)
        self.setTabWidth(4)
        self.setAutoIndent(True)

    def get_code(self) -> str:
        return self.text()

    