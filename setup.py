#!/usr/bin/env python

from distutils.core import setup
import os

def find(path='.'):
	r = []
	for f in os.listdir(path):
		if os.path.isdir(f): r.extend(find(f))
		else: r.append(os.path.join(path, f))
	return r

setup(name='postfix-forward', version='0.1',
	author='Ryan Marquardt',
	author_email='ryan.marquardt@gmail.com',
	description='Installs and manages a forwarding-only postfix email server',
	url='https://github.com/orbnauticus/postfix-forward',
	license='BSD Simplified License',
	scripts=['pff'],
	py_modules=['postfix_forward'],
)
