#!/usr/bin/env python

import os
from pyparsing import *
from base64 import b64decode
from potr.utils import bytes_to_long
from potr.compatcrypto import DSAKey

# much of this is copied and pasted from https://github.com/guardianproject/otrfileconverter 

def verifyLen(t):
  t = t[0]
  if t.len is not None:
    t1len = len(t[1])
    if t1len != t.len:
      raise ParseFatalException, \
        "invalid data of length %d, expected %s" % (t1len, t.len)
  return t[1]

def parse_sexp(data):
  '''parse sexp/S-expression format and return a python list'''
  # define punctuation literals
  LPAR, RPAR, LBRK, RBRK, LBRC, RBRC, VBAR = map(Suppress, "()[]{}|")

  decimal = Word("123456789",nums).setParseAction(lambda t: int(t[0]))
  bytes = Word(printables)
  raw = Group(decimal.setResultsName("len") + Suppress(":") + bytes).setParseAction(verifyLen)
  token = Word(alphanums + "-./_:*+=")
  base64_ = Group(Optional(decimal,default=None).setResultsName("len") + VBAR
    + OneOrMore(Word( alphanums +"+/=" )).setParseAction(lambda t: b64decode("".join(t)))
    + VBAR).setParseAction(verifyLen)

  hexadecimal = ("#" + OneOrMore(Word(hexnums)) + "#")\
    .setParseAction(lambda t: int("".join(t[1:-1]),16))
  qString = Group(Optional(decimal,default=None).setResultsName("len") +
    dblQuotedString.setParseAction(removeQuotes)).setParseAction(verifyLen)
  simpleString = raw | token | base64_ | hexadecimal | qString

  display = LBRK + simpleString + RBRK
  string_ = Optional(display) + simpleString

  sexp = Forward()
  sexpList = Group(LPAR + ZeroOrMore(sexp) + RPAR)
  sexp << ( string_ | sexpList )

  try:
    sexpr = sexp.parseString(data)
    return sexpr.asList()[0][1:]
  except ParseFatalException, pfe:
    print "Error:", pfe.msg
    print line(pfe.loc,t)
    print pfe.markInputline()

def parse(filename):
  '''parse the otr.private_key S-Expression and return an OTR dict'''

  f = open(filename, 'r')
  data = ""
  for line in f.readlines():
    data += line
  f.close()

  sexplist = parse_sexp(data)
  keydict = dict()
  for sexpkey in sexplist:
    if sexpkey[0] == "account":
      key = dict()
      name = ''
      for element in sexpkey:
        # 'name' must be the first element in the sexp or BOOM!
        if element[0] == "name":
          if element[1].find('/') > -1:
            name, resource = element[1].split('/')
          else:
            name = element[1].strip()
            resource = ''
          key = dict()
          key['name'] = name.strip()
          key['resource'] = resource.strip()
        if element[0] == "protocol":
          key['protocol'] = element[1]
        elif element[0] == "private-key":
          if element[1][0] == 'dsa':
            key['type'] = 'dsa';
            for num in element[1][1:6]:
              key[num[0]] = num[1]
      keytuple = (key['y'], key['g'], key['p'], key['q'], key['x'])
      key['dsakey'] = DSAKey(keytuple, private=True)
      key['fingerprint'] = '{0:040x}'.format(bytes_to_long(key['dsakey'].fingerprint()))
      keydict[name] = key
  return keydict

if __name__ == "__main__":
  pidgin_key_filename = os.getenv('HOME')+'/.purple/otr.private_key'
  pidgin_fp_filename = os.getenv('HOME')+'/.purple/otr.fingerprints'

  output_dir = 'output'
  if not os.path.exists(output_dir):
    os.mkdir(output_dir)

  keys = parse(pidgin_key_filename)

  gajim_fps = dict()
  for account in keys:
    gajim_fps[account] = ''

  pidgin_fps = [x.split() for x in open(pidgin_fp_filename)]
  for fp in pidgin_fps:
    if fp[2] == 'prpl-jabber':
      if len(fp) < 5:
        fp.append('')
      fp[1] = fp[1].split('/')[0]
      fp[2] = 'xmpp'
      gajim_fps[fp[1]] += '\t'.join(fp) + '\n'

  for account in keys:
    serialized_private_key = keys[account]['dsakey'].serializePrivateKey()
    open(output_dir+'/'+account+'.key3', 'w').write(serialized_private_key)
    open(output_dir+'/'+account+'.fpr', 'w').write(gajim_fps[account])

