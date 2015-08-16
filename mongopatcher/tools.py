def tabulate(txt):
    return '\t' + '\n\t'.join([l.strip() for l in txt.splitlines()])


def red(txt):
    return colored(txt, '\033[91m')


def green(txt):
    return colored(txt, '\033[92m')


def yellow(txt):
    return colored(txt, '\033[93m')


def colored(txt, color):
    return '%s%s\033[0m' % (color, txt)
