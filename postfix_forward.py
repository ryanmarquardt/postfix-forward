#!/usr/bin/env python

import os
import re
from subprocess import Popen,PIPE
import sys
import termios
import traceback

class namespace(object):
	def __init__(self, **kwargs):
		for k in kwargs:
			setattr(self, k, kwargs[k])

email_regex = '[A-Za-z0-9_+.-]+@[a-zA-Z0-9_+.-]+'
def is_email(s):
	return bool(re.match(email_regex, s))

class DB(object):
	class Field(str): __repr__=str.__str__

	def __init__(self):
		self._depth = 0

	def __enter__(self):
		self._depth += 1
		return self

	def __exit__(self, exc, obj, tb):
		self._depth -= 1
		if self._depth == 0:
			if exc:
				self.rollback()
			else:
				self.commit()

	def commit(self):
		self._conn.commit()

	def rollback(self):
		self._conn.rollback()

	def execute(self, query, values=()):
		cursor = self._conn.cursor()
		with self:
			cursor.execute(query, values)
		return cursor

def EmailField(name):
	return "%s VARCHAR(255) NOT NULL DEFAULT ''" % name

class AuthError(Exception): pass
class DatabaseExists(Exception): pass
class TableExists(Exception): pass

class mysql(DB):
	def __init__(self, **kwargs):
		import MySQLdb
		self._exceptions = namespace(
			OperationalError = MySQLdb.OperationalError,
			ProgrammingError = MySQLdb.ProgrammingError,
		)
		DB.__init__(self)
		try:
			self._conn = MySQLdb.connect(
				host=kwargs.get('host') or 'localhost',
				user=kwargs.get('user') or 'root',
				passwd=kwargs.get('password'),
				db=kwargs.get('db'),
			)
			self._modified_user = False
		except MySQLdb.OperationalError, e:
			if e.args[0] == 1045:
				raise AuthError(e.args[1])
			else:
				raise

	def commit(self):
		if self._modified_user:
			self._modified_user = False
			self.execute('FLUSH PRIVILEGES;')
		DB.commit(self)

	def rollback(self):
		self._modified_user = False
		DB.rollback(self)

	def create_database(self, name):
		try:
			self.execute("CREATE DATABASE %s;" % name)
		except self._exceptions.ProgrammingError, e:
			if e.args[0] == 1007: raise DatabaseExists
			else: raise

	def create_table(self, name, *fields, **options):
		primarykeys = options.get('primarykeys')
		query = ('CREATE TABLE %s ('%name) + ', '.join(fields)
		if primarykeys:
			query += ', PRIMARY KEY (%s)' % ','.join(primarykeys)
		query += ');'
		try:
			self.execute(query)
		except self._exceptions.OperationalError, e:
			if e.args[0] == 1050: raise TableExists
			else: raise

	def create_user(self, user, password, perms, on_table):
		self._modified_user = True
		self.execute('''GRANT %(perms)s ON %(table)s
		TO %(user)s IDENTIFIED BY '%(password)s';''' % {
			'perms':', '.join(perms), 'table':on_table, 'password':password,
			'user':user if '@' in user else user+'@localhost'})

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

	@classmethod
	def viewer(cls, **kwargs):
		user = kwargs.get('user') or viewer.get('user','postfix')
		password = kwargs.get('password') or viewer.get('password') or read_password("Enter mysql password for %s:" % user)
		print user, password
		return cls(host='127.0.0.1', user=user, password=password, db=viewer.get('dbname','postfix'))

	@classmethod
	def editor(cls, **kwargs):
		user = kwargs.get('user') or editor.get('user','postfix_editor')
		password = kwargs.get('password') or editor.get('password') or read_password("Enter mysql password for %s:" % user)
		return cls(host='127.0.0.1', user=user, password=password, db=viewer.get('dbname','postfix'))

	@staticmethod
	def concat(*names):
		return 'CONCAT(%s)' % ','.join(names)

	@staticmethod
	def postfix_conf(args, key, value):
		print dict(args)
		cf_template = '''hosts = 127.0.0.1\nuser = %(view_user)s\npassword = %(view_password)s
dbname = %(database)s\nquery = SELECT %(0)s FROM %(table)s WHERE %(1)s='%%s'\n'''
		params = dict(args.items() + [('0',key),('1',value)])
		return cf_template % params

class Postconf(object):
	def set(self, key, value):
		Popen(['postconf', '-e', '%s = %s' % (key, value)]).communicate()
	__setitem__ = set
	__setattr__ = set

	def get(self, key):
		stdout, stderr = Popen(['postconf','-h',key], stdout=PIPE, stderr=PIPE).communicate()
		if stderr:
			raise KeyError
		else:
			return stdout[:-1]
	__getattr__ = get
	__getitem__ = get

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
	traceback.print_exc()
	viewer = {}
try:
	editor = dict(map(str.strip,line.split('=',1)) for line in open(edit_credentials_path).read().split('\n') if line.strip())
except:
	traceback.print_exc()
	editor = {}

DATABASES = {
	'mysql':mysql,
}
