# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod

"""Font merger.
"""

import sys
import time

import fontTools
from fontTools import misc, ttLib, cffLib

def _add_method(*clazzes):
  """Returns a decorator function that adds a new method to one or
  more classes."""
  def wrapper(method):
    for clazz in clazzes:
      assert clazz.__name__ != 'DefaultTable', 'Oops, table class not found.'
      assert not hasattr(clazz, method.func_name), \
          "Oops, class '%s' has method '%s'." % (clazz.__name__,
                                                 method.func_name)
      setattr(clazz, method.func_name, method)
    return None
  return wrapper


@_add_method(fontTools.ttLib.getTableClass('maxp'))
def merge(self, tables, fonts):
	# TODO When we correctly merge hinting data, update these values:
	# maxFunctionDefs, maxInstructionDefs, maxSizeOfInstructions
	# TODO Assumes that all tables have format 1.0; safe assumption.
	for key in set(sum((vars(table).keys() for table in tables), [])):
			setattr(self, key, max(getattr(table, key) for table in tables))
	return True

@_add_method(fontTools.ttLib.getTableClass('head'))
def merge(self, tables, fonts):
	# TODO Check that unitsPerEm are the same.
	# TODO Use bitwise ops for flags, macStyle, fontDirectionHint
	minMembers = ['xMin', 'yMin']
	# Negate some members
	for key in minMembers:
		for table in tables:
			setattr(table, key, -getattr(table, key))
	# Get max over members
	for key in set(sum((vars(table).keys() for table in tables), [])):
		setattr(self, key, max(getattr(table, key) for table in tables))
	# Negate them back
	for key in minMembers:
		for table in tables:
			setattr(table, key, -getattr(table, key))
		setattr(self, key, -getattr(self, key))
	return True

@_add_method(fontTools.ttLib.getTableClass('hhea'))
def merge(self, tables, fonts):
	# TODO Check that ascent, descent, slope, etc are the same.
	minMembers = ['descent', 'minLeftSideBearing', 'minRightSideBearing']
	# Negate some members
	for key in minMembers:
		for table in tables:
			setattr(table, key, -getattr(table, key))
	# Get max over members
	for key in set(sum((vars(table).keys() for table in tables), [])):
		setattr(self, key, max(getattr(table, key) for table in tables))
	# Negate them back
	for key in minMembers:
		for table in tables:
			setattr(table, key, -getattr(table, key))
		setattr(self, key, -getattr(self, key))
	return True

@_add_method(fontTools.ttLib.getTableClass('post'))
def merge(self, tables, fonts):
	# TODO Check that italicAngle, underlinePosition, underlineThickness are the same.
	minMembers = ['underlinePosition', 'minMemType42', 'minMemType1']
	# Negate some members
	for key in minMembers:
		for table in tables:
			setattr(table, key, -getattr(table, key))
	# Get max over members
	keys = set(sum((vars(table).keys() for table in tables), []))
	if 'mapping' in keys:
		keys.remove('mapping')
	keys.remove('extraNames')
	for key in keys:
		setattr(self, key, max(getattr(table, key) for table in tables))
	# Negate them back
	for key in minMembers:
		for table in tables:
			setattr(table, key, -getattr(table, key))
		setattr(self, key, -getattr(self, key))
	self.mapping = {}
	for table in tables:
		if hasattr(table, 'mapping'):
			self.mapping.update(table.mapping)
	self.extraNames = []
	return True

@_add_method(fontTools.ttLib.getTableClass('vmtx'),
             fontTools.ttLib.getTableClass('hmtx'))
def merge(self, tables, fonts):
	self.metrics = {}
	for table in tables:
		self.metrics.update(table.metrics)
	return True

@_add_method(fontTools.ttLib.getTableClass('loca'))
def merge(self, tables, fonts):
	return True # Will be computed automatically

@_add_method(fontTools.ttLib.getTableClass('glyf'))
def merge(self, tables, fonts):
	self.glyphs = {}
	for table in tables:
		self.glyphs.update(table.glyphs)
	# TODO Drop hints?
	return True

@_add_method(fontTools.ttLib.getTableClass('prep'),
	     fontTools.ttLib.getTableClass('fpgm'),
	     fontTools.ttLib.getTableClass('cvt '))
def merge(self, tables, fonts):
	return False # Will be computed automatically


class Options(object):

  class UnknownOptionError(Exception):
    pass

  _drop_tables_default = ['fpgm', 'prep', 'cvt ', 'gasp']
  drop_tables = _drop_tables_default

  def __init__(self, **kwargs):

    self.set(**kwargs)

  def set(self, **kwargs):
    for k,v in kwargs.iteritems():
      if not hasattr(self, k):
        raise self.UnknownOptionError("Unknown option '%s'" % k)
      setattr(self, k, v)

  def parse_opts(self, argv, ignore_unknown=False):
    ret = []
    opts = {}
    for a in argv:
      orig_a = a
      if not a.startswith('--'):
        ret.append(a)
        continue
      a = a[2:]
      i = a.find('=')
      op = '='
      if i == -1:
        if a.startswith("no-"):
          k = a[3:]
          v = False
        else:
          k = a
          v = True
      else:
        k = a[:i]
        if k[-1] in "-+":
          op = k[-1]+'='  # Ops is '-=' or '+=' now.
          k = k[:-1]
        v = a[i+1:]
      k = k.replace('-', '_')
      if not hasattr(self, k):
        if ignore_unknown == True or k in ignore_unknown:
          ret.append(orig_a)
          continue
        else:
          raise self.UnknownOptionError("Unknown option '%s'" % a)

      ov = getattr(self, k)
      if isinstance(ov, bool):
        v = bool(v)
      elif isinstance(ov, int):
        v = int(v)
      elif isinstance(ov, list):
        vv = v.split(',')
        if vv == ['']:
          vv = []
        vv = [int(x, 0) if len(x) and x[0] in "0123456789" else x for x in vv]
        if op == '=':
          v = vv
        elif op == '+=':
          v = ov
          v.extend(vv)
        elif op == '-=':
          v = ov
          for x in vv:
            if x in v:
              v.remove(x)
        else:
          assert 0

      opts[k] = v
    self.set(**opts)

    return ret


class Merger:

	def __init__(self, options=None, log=None):

		if not log:
			log = Logger()
		if not options:
			options = Options()

		self.options = options
		self.log = log

	def merge(self, fontfiles):

		mega = ttLib.TTFont()

		#
		# Settle on a mega glyph order.
		#
		fonts = [ttLib.TTFont(fontfile) for fontfile in fontfiles]
		glyphOrders = [font.getGlyphOrder() for font in fonts]
		megaGlyphOrder = self._mergeGlyphOrders(glyphOrders)
		# Reload fonts and set new glyph names on them.
		# TODO Is it necessary to reload font?  I think it is.  At least
		# it's safer, in case tables were loaded to provide glyph names.
		fonts = [ttLib.TTFont(fontfile) for fontfile in fontfiles]
		map(ttLib.TTFont.setGlyphOrder, fonts, glyphOrders)
		mega.setGlyphOrder(megaGlyphOrder)

		cmaps = [self._get_cmap(font) for font in fonts]

		allTags = set(sum([font.keys() for font in fonts], []))
		allTags.remove('GlyphOrder')
		for tag in allTags:

			if tag in self.options.drop_tables:
				print "Dropping '%s'." % tag
				continue

			clazz = ttLib.getTableClass(tag)

			if not hasattr(clazz, 'merge'):
				print "Don't know how to merge '%s', dropped." % tag
				continue

			# TODO For now assume all fonts have the same tables.
			tables = [font[tag] for font in fonts]
			table = clazz(tag)
			if table.merge (tables, fonts):
				mega[tag] = table
				print "Merged '%s'." % tag
			else:
				print "Dropped '%s'.  No need to merge explicitly." % tag

		return mega

	def _get_cmap(self, font):
		cmap = font['cmap']
		tables = [t for t in cmap.tables
			    if t.platformID == 3 and t.platEncID in [1, 10]]
		# XXX Handle format=14
		assert len(tables)
		# Pick table that has largest coverage
		table = max(tables, key=lambda t: len(t.cmap))
		return table

	def _mergeGlyphOrders(self, glyphOrders):
		"""Modifies passed-in glyphOrders to reflect new glyph names."""
		# Simply append font index to the glyph name for now.
		mega = []
		for n,glyphOrder in enumerate(glyphOrders):
			for i,glyphName in enumerate(glyphOrder):
				glyphName += "#" + `n`
				glyphOrder[i] = glyphName
				mega.append(glyphName)
		return mega


class Logger(object):

  def __init__(self, verbose=False, xml=False, timing=False):
    self.verbose = verbose
    self.xml = xml
    self.timing = timing
    self.last_time = self.start_time = time.time()

  def parse_opts(self, argv):
    argv = argv[:]
    for v in ['verbose', 'xml', 'timing']:
      if "--"+v in argv:
        setattr(self, v, True)
        argv.remove("--"+v)
    return argv

  def __call__(self, *things):
    if not self.verbose:
      return
    print ' '.join(str(x) for x in things)

  def lapse(self, *things):
    if not self.timing:
      return
    new_time = time.time()
    print "Took %0.3fs to %s" %(new_time - self.last_time,
                                 ' '.join(str(x) for x in things))
    self.last_time = new_time

  def font(self, font, file=sys.stdout):
    if not self.xml:
      return
    from fontTools.misc import xmlWriter
    writer = xmlWriter.XMLWriter(file)
    font.disassembleInstructions = False  # Work around ttLib bug
    for tag in font.keys():
      writer.begintag(tag)
      writer.newline()
      font[tag].toXML(writer, font)
      writer.endtag(tag)
      writer.newline()


__all__ = [
  'Options',
  'Merger',
  'Logger',
  'main'
]

def main(args):

	log = Logger()
	args = log.parse_opts(args)

	options = Options()
	args = options.parse_opts(args)

	if len(args) < 1:
		print >>sys.stderr, "usage: pyftmerge font..."
		sys.exit(1)

	merger = Merger(options=options, log=log)
	font = merger.merge(args)
	outfile = 'merged.ttf'
	font.save(outfile)

if __name__ == "__main__":
	main(sys.argv[1:])
