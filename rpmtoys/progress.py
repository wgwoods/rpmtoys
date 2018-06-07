# progress.py - dumb simple progress meter wrapper

import sys
from time import monotonic
from shutil import get_terminal_size


def progress(iterable,
             prefix="",
             itemfmt=lambda i: str(i),
             interval=0.125,
             out=sys.stdout,
             flush=True):
    items = list(iterable)
    prog = Progress(total=len(items), prefix=prefix, interval=interval,
                    out=out, flush=flush)
    for n, i in enumerate(items):
        prog.item(itemfmt(i))
        yield i
    prog.end()


class Progress(object):
    def __init__(self,
                 total=None,
                 prefix='',
                 maxlen=None,
                 interval=0.125,
                 flush=True,
                 out=sys.stdout):
        self.total = total
        self.prefix = prefix
        self.maxlen = get_terminal_size((maxlen, None)).columns
        self.interval = interval
        self.flush = flush
        self.out = out
        self.count = 0
        self._prev = None
        self._item = None
        self._tlen = None
        self._ilen = None
        self._fmt = "{prefix}[{count:{tlen}}/{total:{tlen}}] ({pct:5}) {item: <{ilen}.{ilen}}"
        self._showts = None
        if total is not None:
            self.start(total)

    def start(self, total):
        self.total = total
        self._tlen = len(str(total))
        self._ilen = 0

    def _fmt_pct(self):
        if not self.total:
            return " ---%"
        pct = self.count/float(self.total)
        return "{:5.1%}".format(pct) if pct < 0.9995 else " 100%"

    def __str__(self):
        return self._fmt.format(count=self.count,
                                total=self.total,
                                prefix=self.prefix,
                                item=self._item or "---",
                                tlen=self._tlen,
                                ilen=self._ilen,
                                pct=self._fmt_pct())[:self.maxlen]

    def _show(self):
        ts = monotonic()
        if self._showts and ts - self._showts < self.interval:
            return
        self._showts = ts
        print("\r"+str(self), end='', file=self.out, flush=self.flush)  # NOQA
        self._prev = self._item

    def item(self, item):
        self.count += 1
        self._item = item
        self._ilen = max(self._ilen, len(item))  # set new ilen if longer
        self._show()

    def end(self):
        self._showts = 0
        self._show()
        print()
