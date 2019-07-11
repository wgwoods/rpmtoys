# progress.py - dumb simple progress meter wrapper

import sys
from time import monotonic
from shutil import get_terminal_size

def progress(iterable,
             prefix="",
             itemfmt=lambda i: str(i),
             countmsg=None,
             interval=0.125,
             out=sys.stdout,
             flush=True):
    prog = Progress(prefix=prefix, interval=interval, out=out, flush=flush)
    items = prog.count_then_start(iterable, countmsg=countmsg)
    for i in items:
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
        self._item = None
        self._ilen = None
        self._fmt = "{prefix}[{count:{tlen}}/{total:{tlen}}] ({pct:5}) {item: <{ilen}.{ilen}}"
        self._showts = None
        if total is not None:
            self.start(total)

    def count_then_start(self, iterable, countmsg=None):
        '''
        Count the items in iterable, set total, and return a list of items.
        If this takes longer than interval, show progress while counting.
        '''
        # Fake timestamp so nothing happens in the first interval
        count_ts = monotonic()
        self._showts = count_ts
        # set count, total, item
        self.count = 0
        self.total = 0
        self._item = countmsg if countmsg is not None else "gathering items..."
        self._ilen = len(self._item)
        # Gather iterable into a list, showing progress as we count
        items = list()
        for i in iterable:
            items.append(i)
            self.total += 1
            self._show()
        # If we showed the countmsg, update it to the right total
        if self._showts > count_ts:
            self._showts = 0
            self._show()
        # Return the gathered list
        return items

    @property
    def _tlen(self):
        return len(str(self.total))

    def start(self, total):
        self.total = total
        self._ilen = 0

    def _fmt_pct(self):
        if not self.total:
            return " ---%"
        pct = self.count/float(self.total)
        return "{:5.1%}".format(pct) if pct < 0.9995 else " 100%"

    def __str__(self):
        return self._fmt.format(count=self.count,
                                total=self.total or 0,
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

    def item(self, item):
        self.count += 1
        self._item = item
        self._ilen = max(self._ilen or 0, len(item))  # set new ilen if longer
        self._show()

    def end(self):
        self._showts = 0
        self._show()
        print(file=self.out, flush=True)
