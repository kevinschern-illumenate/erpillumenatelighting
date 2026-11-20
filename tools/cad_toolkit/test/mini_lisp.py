"""A small AutoLISP interpreter for CI (draw-to-quote plan 3.10).

AutoCAD cannot run in GitHub CI, so the toolkit keeps its math, JSON, catalog and package code in pure
AutoLISP files (il-util, il-json, il-math, il-catalog, il-model) and this interpreter runs them against
the shared fixtures. It implements only the subset those files use, with AutoLISP's semantics where
they matter: dynamic scope, integer division, 32-bit integers, case-insensitive symbols, nil as the
empty list, dotted pairs, ``vl-catch-all-apply``, files read line by line. The release check is still
``accoreconsole`` in real AutoCAD (``tools/cad_toolkit/test/run_tests.scr``); this is the fast gate.
"""

import functools
import itertools
import math
import re
import typing


class Sym:
	__slots__ = ("name",)
	_table: typing.ClassVar[dict] = {}

	def __new__(cls, name):
		name = name.upper()
		if name not in cls._table:
			obj = super().__new__(cls)
			obj.name = name
			cls._table[name] = obj
		return cls._table[name]

	def __repr__(self):
		return self.name


T = Sym("T")


class Pair:
	"""A dotted pair whose cdr is not a list."""

	__slots__ = ("car", "cdr")

	def __init__(self, car, cdr):
		self.car, self.cdr = car, cdr

	def __eq__(self, other):
		return isinstance(other, Pair) and lisp_equal(self.car, other.car) and lisp_equal(self.cdr, other.cdr)

	def __repr__(self):
		return f"({self.car!r} . {self.cdr!r})"


class LispError(Exception):
	pass


class CaughtError:
	def __init__(self, message):
		self.message = message


class Function:
	def __init__(self, name, params, local_names, body):
		self.name, self.params, self.locals, self.body = name, params, local_names, body


class FileHandle:
	def __init__(self, path, mode):
		self.handle = open(path, {"r": "r", "w": "w", "a": "a"}[mode], encoding="utf-8", newline="")

	def read_line(self):
		line = self.handle.readline()
		if line == "":
			return None
		return line.rstrip("\r\n")


def lst(items):
	items = list(items)
	return items if items else None


def is_list(value):
	return value is None or isinstance(value, list)


def truthy(value):
	return value is not None


def wrap_int(value):
	value &= 0xFFFFFFFF
	return value - 0x100000000 if value & 0x80000000 else value


def lisp_equal(a, b, fuzz=0.0):
	if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
		return abs(a - b) <= fuzz if fuzz else a == b
	if isinstance(a, list) and isinstance(b, list):
		return len(a) == len(b) and all(lisp_equal(x, y, fuzz) for x, y in zip(a, b, strict=True))
	if isinstance(a, Pair) or isinstance(b, Pair):
		return isinstance(a, Pair) and isinstance(b, Pair) and lisp_equal(a.car, b.car, fuzz) and lisp_equal(a.cdr, b.cdr, fuzz)
	return a is b or (type(a) is type(b) and a == b)


# --- Reader -----------------------------------------------------------------------------------

TOKEN = re.compile(r'\s+|;\|.*?\|;|;[^\n]*|"(?:\\.|[^"\\])*"|[()\']|[^\s()\'";]+', re.S)
ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "e": "\x1b", "\\": "\\", '"': '"'}


def tokenize(text):
	for match in TOKEN.finditer(text):
		token = match.group(0)
		if token.isspace() or token.startswith(";"):
			continue
		yield token


def unescape(body):
	out, index = [], 0
	while index < len(body):
		char = body[index]
		if char == "\\" and index + 1 < len(body):
			nxt = body[index + 1]
			if nxt.isdigit():
				digits = re.match(r"[0-7]{1,3}", body[index + 1 :]).group(0)
				out.append(chr(int(digits, 8)))
				index += 1 + len(digits)
				continue
			out.append(ESCAPES.get(nxt, nxt))
			index += 2
			continue
		out.append(char)
		index += 1
	return "".join(out)


def atom(token):
	if token.startswith('"'):
		return unescape(token[1:-1])
	if re.fullmatch(r"[+-]?\d+", token):
		return wrap_int(int(token))
	if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", token):
		return float(token)
	symbol = Sym(token)
	return None if symbol.name == "NIL" else symbol


def read_all(text):
	tokens = list(tokenize(text))
	position = 0

	def read():
		nonlocal position
		token = tokens[position]
		position += 1
		if token == "'":
			return [Sym("QUOTE"), read()]
		if token == "(":
			items = []
			while tokens[position] != ")":
				if tokens[position] == ".":
					position += 1
					tail = read()
					position += 1  # ")"
					return cons_many(items, tail)
				items.append(read())
			position += 1
			return lst(items)
		if token == ")":
			raise LispError("unexpected )")
		return atom(token)

	forms = []
	while position < len(tokens):
		forms.append(read())
	return forms


def cons_many(items, tail):
	result = tail
	for item in reversed(items):
		result = cons(item, result)
	return result


def cons(a, b):
	if b is None:
		return [a]
	if isinstance(b, list):
		return [a, *b]
	return Pair(a, b)


def car(value):
	if value is None:
		return None
	if isinstance(value, Pair):
		return value.car
	if isinstance(value, list):
		return value[0]
	raise LispError(f"bad argument type: consp {value!r}")


def cdr(value):
	if value is None:
		return None
	if isinstance(value, Pair):
		return value.cdr
	if isinstance(value, list):
		return lst(value[1:])
	raise LispError(f"bad argument type: consp {value!r}")


# --- Interpreter ------------------------------------------------------------------------------


class Exit(Exception):
	pass


class Interpreter:
	def __init__(self):
		self.globals = {}
		self.builtins = builtins(self)

	def load(self, path):
		with open(path, encoding="utf-8") as handle:
			text = handle.read()
		result = None
		for form in read_all(text):
			result = self.eval(form)
		return result

	def run(self, text):
		result = None
		for form in read_all(text):
			result = self.eval(form)
		return result

	def call(self, name, *args):
		return self.apply(self.function(Sym(name)), list(args))

	def get(self, name):
		return self.globals.get(Sym(name))

	def set(self, name, value):
		self.globals[Sym(name)] = value

	def function(self, head):
		if isinstance(head, Sym):
			value = self.globals.get(head)
			if isinstance(value, Function) or callable(value):
				return value
			if head in self.builtins:
				return self.builtins[head]
			raise LispError(f"no function definition: {head.name}")
		if isinstance(head, list) and head and head[0] is Sym("LAMBDA"):
			return self.eval(head)
		if isinstance(head, Function) or callable(head):
			return head
		raise LispError(f"bad function: {head!r}")

	def eval(self, form):
		if isinstance(form, Sym):
			if form is T:
				return T
			return self.globals.get(form)
		if not isinstance(form, list):
			return form
		head = form[0]
		if isinstance(head, Sym):
			special = SPECIAL.get(head.name)
			if special:
				return special(self, form[1:])
		function = self.function(head)
		args = [self.eval(arg) for arg in form[1:]]
		return self.apply(function, args)

	def apply(self, function, args):
		if callable(function):
			return function(*args)
		saved = {}
		names = function.params + function.locals
		for name in names:
			saved[name] = self.globals.get(name, _UNBOUND)
		try:
			for index, name in enumerate(function.params):
				self.globals[name] = args[index] if index < len(args) else None
			for name in function.locals:
				self.globals[name] = None
			result = None
			for form in function.body:
				result = self.eval(form)
			return result
		finally:
			for name, value in saved.items():
				if value is _UNBOUND:
					self.globals.pop(name, None)
				else:
					self.globals[name] = value


_UNBOUND = object()


def parse_params(spec):
	params, local_names, in_locals = [], [], False
	for item in spec or []:
		if item is Sym("/"):
			in_locals = True
			continue
		(local_names if in_locals else params).append(item)
	return params, local_names


def sf_quote(interp, args):
	return args[0]


def sf_setq(interp, args):
	value = None
	for index in range(0, len(args), 2):
		value = interp.eval(args[index + 1])
		interp.globals[args[index]] = value
	return value


def sf_if(interp, args):
	if truthy(interp.eval(args[0])):
		return interp.eval(args[1])
	return interp.eval(args[2]) if len(args) > 2 else None


def sf_cond(interp, args):
	for clause in args:
		test = interp.eval(clause[0])
		if truthy(test):
			result = test
			for form in clause[1:]:
				result = interp.eval(form)
			return result
	return None


def sf_while(interp, args):
	result = None
	while truthy(interp.eval(args[0])):
		for form in args[1:]:
			result = interp.eval(form)
	return result


def sf_repeat(interp, args):
	result = None
	for _ in range(int(interp.eval(args[0]))):
		for form in args[1:]:
			result = interp.eval(form)
	return result


def sf_foreach(interp, args):
	name, items = args[0], interp.eval(args[1])
	saved = interp.globals.get(name, _UNBOUND)
	result = None
	try:
		for item in items or []:
			interp.globals[name] = item
			for form in args[2:]:
				result = interp.eval(form)
	finally:
		if saved is _UNBOUND:
			interp.globals.pop(name, None)
		else:
			interp.globals[name] = saved
	return result


def sf_progn(interp, args):
	result = None
	for form in args:
		result = interp.eval(form)
	return result


def sf_and(interp, args):
	for form in args:
		if not truthy(interp.eval(form)):
			return None
	return T


def sf_or(interp, args):
	for form in args:
		if truthy(interp.eval(form)):
			return T
	return None


def sf_defun(interp, args):
	name = args[0]
	params, local_names = parse_params(args[1])
	interp.globals[name] = Function(name.name, params, local_names, args[2:])
	return name


def sf_lambda(interp, args):
	params, local_names = parse_params(args[0])
	return Function("lambda", params, local_names, args[1:])


def sf_function(interp, args):
	value = args[0]
	if isinstance(value, list) and value[0] is Sym("LAMBDA"):
		return interp.eval(value)
	return value


SPECIAL = {
	"QUOTE": sf_quote,
	"SETQ": sf_setq,
	"IF": sf_if,
	"COND": sf_cond,
	"WHILE": sf_while,
	"REPEAT": sf_repeat,
	"FOREACH": sf_foreach,
	"PROGN": sf_progn,
	"AND": sf_and,
	"OR": sf_or,
	"DEFUN": sf_defun,
	"LAMBDA": sf_lambda,
	"FUNCTION": sf_function,
}


def num(value):
	if isinstance(value, (int, float)):
		return value
	raise LispError(f"bad argument type: numberp: {value!r}")


def arith(op, values):
	values = [num(v) for v in values]
	if all(isinstance(v, int) for v in values):
		result = values[0]
		for v in values[1:]:
			if op == "/":
				if v == 0:
					raise LispError("divide by zero")
				result = int(result / v)
			else:
				result = {"+": result + v, "-": result - v, "*": result * v}[op]
		return wrap_int(result)
	result = float(values[0])
	for v in values[1:]:
		if op == "/":
			if v == 0:
				raise LispError("divide by zero")
			result /= v
		else:
			result = {"+": result + v, "-": result - v, "*": result * v}[op]
	return result


def compare(op, values):
	for a, b in itertools.pairwise(values):
		if not op(a, b):
			return None
	return T


def lisp_type(value):
	if value is None:
		return None
	if isinstance(value, bool):
		return Sym("SYM")
	if isinstance(value, int):
		return Sym("INT")
	if isinstance(value, float):
		return Sym("REAL")
	if isinstance(value, str):
		return Sym("STR")
	if isinstance(value, (list, Pair)):
		return Sym("LIST")
	if isinstance(value, Sym):
		return Sym("SYM")
	if isinstance(value, Function):
		return Sym("USUBR")
	if isinstance(value, FileHandle):
		return Sym("FILE")
	return Sym("SUBR")


def princ_text(value, readable=False):
	if value is None:
		return "nil"
	if isinstance(value, str):
		return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"' if readable else value
	if isinstance(value, float):
		text = f"{value:.6f}".rstrip("0")
		return text + "0" if text.endswith(".") else text
	if isinstance(value, list):
		return "(" + " ".join(princ_text(v, True) for v in value) + ")"
	if isinstance(value, Pair):
		return f"({princ_text(value.car, True)} . {princ_text(value.cdr, True)})"
	if isinstance(value, Sym):
		return value.name
	return str(value)


def builtins(interp):
	def mapcar(function, *lists):
		function = interp.function(function) if not isinstance(function, Function) else function
		lists = [list(items or []) for items in lists]
		return lst(interp.apply(function, list(args)) for args in zip(*lists, strict=False))

	def apply_(function, args):
		return interp.apply(interp.function(function) if not isinstance(function, Function) else function, list(args or []))

	def catch_apply(function, args):
		try:
			return apply_(function, args)
		except (LispError, Exit, ZeroDivisionError, ValueError, TypeError, IndexError) as error:
			return CaughtError(str(error) or "quit / exit abort")

	def substr(text, start, length=None):
		begin = max(start - 1, 0)
		return text[begin:] if length is None else text[begin : begin + length]

	def search(pattern, text, start=0):
		at = text.find(pattern, start)
		return None if at < 0 else at

	def rtos(value, mode=2, precision=4):
		return f"{float(value):.{int(precision)}f}"

	def atoi(text):
		match = re.match(r"\s*[+-]?\d+", text)
		return wrap_int(int(match.group(0))) if match else 0

	def atof(text):
		match = re.match(r"\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", text)
		return float(match.group(0)) if match else 0.0

	def member(item, items):
		items = list(items or [])
		for index, value in enumerate(items):
			if lisp_equal(item, value):
				return lst(items[index:])
		return None

	def assoc(key, items):
		for item in items or []:
			if (isinstance(item, Pair) and lisp_equal(item.car, key)) or (
				isinstance(item, list) and item and lisp_equal(item[0], key)
			):
				return item
		return None

	def subst(new, old, items):
		if items is None:
			return None
		return lst(new if lisp_equal(item, old) else item for item in items)

	def nth(index, items):
		items = items or []
		return items[index] if 0 <= index < len(items) else None

	def last(items):
		return items[-1] if items else None

	def append(*lists):
		out = []
		for items in lists:
			out.extend(items or [])
		return lst(out)

	def open_(path, mode):
		try:
			return FileHandle(path, mode.lower())
		except OSError:
			return None

	def read_line(handle=None):
		return handle.read_line() if handle else None

	def write_line(text, handle=None):
		if handle:
			handle.handle.write(text + "\n")
		return text

	def princ(value=None, handle=None):
		if handle:
			handle.handle.write(princ_text(value))
		return value

	def close(handle):
		handle.handle.close()

	def exit_():
		raise Exit("quit / exit abort")

	def call(function, *args):
		function = interp.function(function) if not isinstance(function, Function) else function
		return interp.apply(function, list(args))

	def vl_sort(items, test):
		# Insertion sort with the LISP predicate (AutoLISP's vl-sort also drops duplicate numbers; the
		# toolkit sorts ids and records, which are distinct).
		result = []
		for item in items or []:
			index = len(result)
			while index > 0 and truthy(call(test, item, result[index - 1])):
				index -= 1
			result.insert(index, item)
		return lst(result)

	def vl_some(test, *lists):
		for args in zip(*[list(items or []) for items in lists], strict=False):
			value = call(test, *args)
			if truthy(value):
				return value
		return None

	def vl_remove_if(test, items):
		return lst(item for item in items or [] if not truthy(call(test, item)))

	def vl_remove_if_not(test, items):
		return lst(item for item in items or [] if truthy(call(test, item)))

	def vl_position(item, items):
		for index, value in enumerate(items or []):
			if lisp_equal(item, value):
				return index
		return None

	def boole(operator, *values):
		# Operator bits: 1 when both bits are 1, 2 for (1, 0), 4 for (0, 1), 8 when both are 0.
		masks = {(1, 1): 1, (1, 0): 2, (0, 1): 4, (0, 0): 8}
		result = values[0] & 0xFFFFFFFF
		for value in values[1:]:
			value &= 0xFFFFFFFF
			result = sum(
				1 << bit for bit in range(32) if operator & masks[((result >> bit) & 1, (value >> bit) & 1)]
			)
		return wrap_int(result)

	def distance(a, b):
		return math.dist([float(x) for x in a[:2]], [float(x) for x in b[:2]])

	def trim(chars, text):
		return text.strip(chars)

	table = {
		"+": lambda *v: arith("+", v) if v else 0,
		"-": lambda *v: arith("-", [0, *v]) if len(v) == 1 else arith("-", v),
		"*": lambda *v: arith("*", v) if v else 1,
		"/": lambda *v: arith("/", v),
		"1+": lambda v: arith("+", [v, 1]),
		"1-": lambda v: arith("-", [v, 1]),
		"=": lambda *v: compare(lambda a, b: a == b, v),
		"/=": lambda *v: compare(lambda a, b: a != b, v),
		"<": lambda *v: compare(lambda a, b: a < b, v),
		">": lambda *v: compare(lambda a, b: a > b, v),
		"<=": lambda *v: compare(lambda a, b: a <= b, v),
		">=": lambda *v: compare(lambda a, b: a >= b, v),
		"ABS": lambda v: abs(num(v)),
		"FIX": lambda v: wrap_int(int(num(v))),
		"FLOAT": lambda v: float(num(v)),
		"REM": lambda a, b: wrap_int(int(math.fmod(a, b))) if isinstance(a, int) and isinstance(b, int) else math.fmod(a, b),
		"EXPT": lambda a, b: wrap_int(a**b) if isinstance(a, int) and isinstance(b, int) and b >= 0 else float(a) ** b,
		"SQRT": lambda v: math.sqrt(v),
		"SIN": math.sin,
		"COS": math.cos,
		"ATAN": lambda a, b=None: math.atan(a) if b is None else math.atan2(a, b),
		"MIN": lambda *v: arith("+", [min(v), 0]) if all(isinstance(x, int) for x in v) else float(min(v)),
		"MAX": lambda *v: arith("+", [max(v), 0]) if all(isinstance(x, int) for x in v) else float(max(v)),
		"MINUSP": lambda v: T if num(v) < 0 else None,
		"ZEROP": lambda v: T if num(v) == 0 else None,
		"NUMBERP": lambda v: T if isinstance(v, (int, float)) else None,
		"EQ": lambda a, b: T if (a is b or (isinstance(a, (int, float)) and a == b)) else None,
		"EQUAL": lambda a, b, fuzz=0.0: T if lisp_equal(a, b, fuzz) else None,
		"NOT": lambda v: T if v is None else None,
		"NULL": lambda v: T if v is None else None,
		"LISTP": lambda v: T if is_list(v) or isinstance(v, Pair) else None,
		"ATOM": lambda v: None if isinstance(v, (list, Pair)) else T,
		"TYPE": lisp_type,
		"CAR": car,
		"CDR": cdr,
		"CADR": lambda v: car(cdr(v)),
		"CADDR": lambda v: car(cdr(cdr(v))),
		"CDDR": lambda v: cdr(cdr(v)),
		"CADDDR": lambda v: car(cdr(cdr(cdr(v)))),
		"CDDDDR": lambda v: cdr(cdr(cdr(cdr(v)))),
		"LOGAND": lambda *v: wrap_int(functools.reduce(lambda a, b: a & b, [x & 0xFFFFFFFF for x in v], 0xFFFFFFFF)),
		"LOGIOR": lambda *v: wrap_int(functools.reduce(lambda a, b: a | b, [x & 0xFFFFFFFF for x in v], 0)),
		"LSH": lambda x, n=0: wrap_int(((x & 0xFFFFFFFF) << n) if n >= 0 else ((x & 0xFFFFFFFF) >> -n)),
		"~": lambda x: wrap_int(~x),
		"BOOLE": boole,
		"CAAR": lambda v: car(car(v)),
		"CDAR": lambda v: cdr(car(v)),
		"LAST": last,
		"NTH": nth,
		"LENGTH": lambda v: len(v or []),
		"CONS": cons,
		"LIST": lambda *v: lst(v),
		"APPEND": append,
		"REVERSE": lambda v: lst(reversed(v or [])),
		"ASSOC": assoc,
		"MEMBER": member,
		"SUBST": subst,
		"MAPCAR": mapcar,
		"APPLY": apply_,
		"STRCAT": lambda *v: "".join(v),
		"SUBSTR": substr,
		"STRLEN": lambda *v: sum(len(x) for x in v),
		"ASCII": lambda v: ord(v[0]) if v else 0,
		"CHR": chr,
		"ITOA": lambda v: str(v),
		"ATOI": atoi,
		"ATOF": atof,
		"RTOS": rtos,
		"STRCASE": lambda text, lower=None: text.lower() if lower is not None else text.upper(),
		"VL-STRING-SEARCH": search,
		"VL-STRING-TRIM": trim,
		"VL-STRING-RIGHT-TRIM": lambda chars, text: text.rstrip(chars),
		"VL-STRING-LEFT-TRIM": lambda chars, text: text.lstrip(chars),
		"VL-PRINC-TO-STRING": lambda v: princ_text(v),
		"VL-SORT": vl_sort,
		"VL-SOME": vl_some,
		"VL-REMOVE-IF": vl_remove_if,
		"VL-REMOVE-IF-NOT": vl_remove_if_not,
		"VL-REMOVE": lambda item, items: lst(value for value in items or [] if not lisp_equal(item, value)),
		"VL-POSITION": vl_position,
		"VL-CATCH-ALL-APPLY": catch_apply,
		"VL-CATCH-ALL-ERROR-P": lambda v: T if isinstance(v, CaughtError) else None,
		"VL-CATCH-ALL-ERROR-MESSAGE": lambda v: v.message,
		"DISTANCE": distance,
		"OPEN": open_,
		"CLOSE": close,
		"READ-LINE": read_line,
		"WRITE-LINE": write_line,
		"PRINC": princ,
		"PRIN1": princ,
		"PRINT": princ,
		"EXIT": exit_,
		"QUIT": exit_,
	}
	return {Sym(name): function for name, function in table.items()}


# --- Conversions for tests ----------------------------------------------------------------------

OBJ, ARR, TRUE, FALSE = Sym("IL-OBJ"), Sym("IL-ARR"), Sym("IL-TRUE"), Sym("IL-FALSE")


def to_python_json(value):
	"""An il-json value as Python (objects, arrays, true/false, null)."""
	if value is None:
		return None
	if value is TRUE:
		return True
	if value is FALSE:
		return False
	if isinstance(value, list) and value and value[0] is OBJ:
		return {pair.car if isinstance(pair, Pair) else pair[0]: to_python_json(pair.cdr if isinstance(pair, Pair) else lst(pair[1:])) for pair in value[1:]}
	if isinstance(value, list) and value and value[0] is ARR:
		return [to_python_json(item) for item in value[1:]]
	return value


def from_python_json(value):
	if value is None:
		return None
	if value is True:
		return TRUE
	if value is False:
		return FALSE
	if isinstance(value, dict):
		return [OBJ, *(cons(key, from_python_json(item)) for key, item in value.items())]
	if isinstance(value, list):
		return [ARR, *(from_python_json(item) for item in value)]
	if isinstance(value, int) and not isinstance(value, bool):
		return wrap_int(value)
	return value


def alist(value):
	"""An association list ((key . value) ...) as a dict (values left as LISP data)."""
	result = {}
	for pair in value or []:
		if isinstance(pair, Pair):
			result[pair.car] = pair.cdr
		else:
			result[pair[0]] = lst(pair[1:])
	return result


def to_alist(mapping):
	return lst(cons(key, item) for key, item in mapping.items())
