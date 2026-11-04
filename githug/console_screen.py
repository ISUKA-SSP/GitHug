"""VT decoding is separate from Tk, so redraws, progress lines and Unicode can be tested."""
import pyte

class ConsoleScreen(pyte.HistoryScreen):
    def __init__(self,columns=100,lines=12,respond=lambda text:None):
        self.respond=respond
        super().__init__(columns,lines,history=1500)

    def write_process_input(self,data):self.respond(data)

    def text(self):
        history=[''.join(row[x].data for x in range(self.columns)).rstrip() for row in self.history.top]
        return '\n'.join(history+[line.rstrip() for line in self.display])
