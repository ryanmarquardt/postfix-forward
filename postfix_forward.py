#!/usr/bin/env python

import MySQLdb
import os
import sys
import termios

def read_password(prompt, f=sys.stdin):
	try:
		new,old = termios.tcgetattr(f),termios.tcgetattr(f)
		new[3] &= ~termios.ECHO
		termios.tcsetattr(sys.stdin, termios.TCSANOW, new)
		r = raw_input(prompt)
		print
	finally:
		termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, old)
	return r

postfix_conf_dir = '/etc/postfix/vhost'
alias_path = os.path.join(postfix_conf_dir, 'aliases.cf')
edit_credentials_path = os.path.join(postfix_conf_dir, 'edit_credentials.cf')
try:
	viewer = dict(map(str.strip,line.split('=',1)) for line in open(alias_path).read().split('\n') if line.strip())
except:
	viewer = {}
try:
	editor = dict(map(str.strip,line.split('=',1)) for line in open(edit_credentials_path).read().split('\n') if line.strip())
except:
	editor = {}

def concat(*names):
	return 'CONCAT(%s)' % ','.join(map(repr,names))

class Expression(list):
	def __init__(self, *tokens): list.__init__(self, tokens)
	def __repr__(self): return ''.join(self)

	def __eq__(self, x): return self + Expression('=') + Expression(x)

class Field(Expression):
	def __init__(self, name, type=str, length=512, notnull=False, default=None, required=False):
		self.name = name
		self.type = type
		self.length = length
		self.notnull = ' NOT NULL' if notnull else ''
		self.default = ' DEFAULT %r' % default if not required else ''
		self.required = required
		self.type_name = {
			str:'VARCHAR(%s)'
		}[type] % vars(self)

	def sql(self):
		return '%(name)s %(type_name)s%(notnull)s%(default)s' % vars(self)

	def __str__(self):
		return self.name

class DB(object):
	def __init__(self):
		self._depth = 0

	def __enter__(self):
		self._depth += 1

	def __exit__(self, exc, obj, tb):
		self._depth -= 1
		if self._depth == 0:
			if exc:
				self._conn.rollback()
			else:
				self._conn.commit()

	def __getattr__(self, name):
		if name not in self.__dict__:
			return Table(self, name)

	def execute(self, query, values=()):
		cursor = self._conn.cursor()
		with self:
			cursor.execute(query, values)
		return cursor

class Table(object):
	def __init__(self, db, name):
		self._db = db
		self._name = name

	def insert(self, **values):
		self._db.insert(self._name, **values)

	def __getattr__(self, name):
		if name not in self.__dict__:
			return Field(self, name)

class mysql(DB):
	def __init__(self, host='localhost', user='root', passwd=None, db=''):
		DB.__init__(self)
		self.user = user
		self.passwd = passwd
		self._conn = MySQLdb.connect(host=host, user=user, passwd=passwd, db=db)

	def create_database(self, name):
		self.execute("CREATE DATABASE %s;" % name)

	def create_table(self, name, *fields, **options):
		primarykeys = options.get('primarykeys')
		query = ('CREATE TABLE %s ('%name) + ', '.join(fields)
		if primarykeys:
			query += ', PRIMARY KEY (%s)' % ','.join(primarykeys)
		query += ');'
		self.execute(query)

	def insert(self, table, **values):
		query = "INSERT INTO %(table)s(%(names)s) VALUES(%(values)s) \
ON DUPLICATE KEY UPDATE %(update)s;" % {
			'table':table,
			'names':','.join(values.keys()),
			'values':','.join(['%s']*len(values)),
			'update':', '.join('%s=%%s'%key for key in values.keys())
		}
		self.execute(query, values.values()*2)

	def select(self, table, *fields, **where):
		query = "SELECT %(fields)s FROM %(table)s %(where)s;" % {
			'fields':','.join(fields),
			'table':table,
			'where':('WHERE '+' AND '.join('%s=%%s'%key for key in where.keys())) if where else '',
		}
		return iter(self.execute(query, where.values()).fetchall())

	def delete(self, table, **where):
		query = "DELETE FROM %(table)s %(where)s;" % {
			'table':table,
			'where':('WHERE '+' AND '.join('%s=%%s'%key for key in where.keys())) if where else '',
		}
		self.execute(query, where.values())

def mysql_viewer(user=None, passwd=None):
	user = user or viewer.get('user','postfix')
	passwd = passwd or viewer.get('password') or read_password("Enter mysql password for %s:" % user)
	return mysql(host='127.0.0.1', user=user, passwd=passwd, db=viewer.get('dbname','postfix'))

def mysql_editor(user=None, passwd=None):
	user = user or editor.get('user','postfix_editor')
	passwd = passwd or editor.get('password') or read_password("Enter mysql password for %s:" % user)
	return mysql(host='127.0.0.1', user=user, passwd=passwd, db=viewer.get('dbname','postfix'))
