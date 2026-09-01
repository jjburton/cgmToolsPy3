
# IMPORTS ====================================================================
import unittest
import unittest.runner
import maya.standalone
import pprint
import logging
import time
import sys
import importlib
import cgm.core.cgm_General as cgmGEN
import cgm.core.cgmPy.path_Utils as PATH
import cgm.core.cgmPy.validateArgs as VALID

import maya.cmds as mc

def sceneSetup():
	try:mc.file(new=True,f=True)
	except Exception as err:
		log.error("New File fail!")
		for arg in err.args:
			log.error(arg)                
		raise err   

# LOGGING ====================================================================
log = logging.getLogger(__name__.split('.')[-1])
log.setLevel(logging.INFO)
#_d_moduleRoots = {'cgmMeta':"cgm.core.tests.test_cgmMeta.test",


_d_modules = {'cgmMeta':['base','mClasses'],
              'coreLib':['LISTS','PATH','ATTR','VALID','NODEFACTORY','DIST','MATH','SHARED','NAMES','GUI','RIGGING','CURVES','SKIN','NODES','ANIMCLIP','SEARCH','SNAP','TEXTURE','UISMOKE'],
              # MRS RigBlocks suite is incomplete (selection leaks + xform on attr plugs).
              # Left in the dict so the Unittesting menu can still list it; skipped from 'all'.
              'MRS':['RigBlocks']}
_l_all_order = ['coreLib','cgmMeta']

def print_suite(suite):
	"""
	https://stackoverflow.com/questions/24478727/how-to-list-available-tests-with-python
	"""
	if hasattr(suite, '__iter__'):
		for x in suite:
			print_suite(x)
	else:
		print(suite)


def _exc_headline(err):
	"""Last non-empty line of a unittest traceback (the AssertionError / exception)."""
	if not err:
		return ''
	lines = [l.strip() for l in str(err).splitlines() if l.strip()]
	return lines[-1] if lines else ''


def _collect_result_rows(mod, result):
	rows = []
	for test, err in result.failures:
		rows.append(('FAIL', mod, test.id(), _exc_headline(err)))
	for test, err in result.errors:
		rows.append(('ERROR', mod, test.id(), _exc_headline(err)))
	return rows


def _print_run_summary(tests_run, n_modules, elapsed, n_fail, n_error, n_skip, rows):
	print((cgmGEN._str_hardBreak))
	print(('Ran {0} tests in {1} modules | {2} seconds'.format(
		tests_run, n_modules, '%0.3f' % elapsed)))
	print(('FAIL: {0}  ERROR: {1}  SKIP: {2}'.format(n_fail, n_error, n_skip)))
	if n_fail or n_error:
		print('RESULT: FAIL')
		for kind, mod, test_id, headline in rows:
			print(('{0}  {1}  {2}'.format(kind, mod, test_id)))
			if headline:
				print(('      {0}'.format(headline)))
	else:
		print('RESULT: PASS')
	print((cgmGEN._str_hardBreak))

		
def main(tests = 'all', verbosity = 1, testCheck = False, **kwargs):	
	"""
	Core test runner for us.

	:parameters:
	    tests(list): Str list of tests to be run. Should be in data lists above in the module. 'all' will run all found tests.
	    verbosity(int): 1,2
	    testCheck(bool): If True, no tests will run it will just collect the list so you can see what would have run

	NOTE: A real run calls mc.file(new=True) and wipes the current scene. LISTS tests are Maya-free
	(no nodes) but still run after that new-file. Use testCheck=True to list without wiping.
	A real run prints a PASS/FAIL rollup at the end (module + test id + exception headline).

	"""   
	
	
	
	v = verbosity
	#mc.scriptEditorInfo(clearHistory=True)
	
	tests = VALID.listArg(tests)

	_l_testModules = []
	_d_testModulePaths = {}
	_d_tests = {}

	#...gather up our tests and paths...
	if tests == ['all']:
		log.info("testing all")
		for m in _l_all_order:
			#log.info(m)
			_tests = _d_modules.get(m,False)
			for t in _tests:
				_key = "{0}.{1}".format(m,t)                
				_l_testModules.append(t)
				_d_testModulePaths[t] = "test_{0}.test_{1}".format(m,t)                    
	else:
		for t in tests:
			for k,l in list(_d_modules.items()):
				if t == k:
					for t2 in l:
						_key = "{0}.{1}".format(k,t2)                        
						_l_testModules.append(_key)
						_d_testModulePaths[_key] = "test_{0}.test_{1}".format(k,t2)                        
				if t in l:
					_key = "{0}.{1}".format(k,t)
					_l_testModules.append(_key)
					_d_testModulePaths[_key] = "test_{0}.test_{1}".format(k,t)

	#cgmGEN.log_info_dict(_d_testModulePaths)

	if not _l_testModules:
		raise ValueError("No modules detected to test. Test arg: {0}".format(tests))

	#....meat of it...
	if testCheck is not True:
		import cgm
		cgm.core._reload()

	_t_start = time.time()
	_len_all = 0
	_tests_run = 0
	_n_fail = 0
	_n_error = 0
	_n_skip = 0
	_l_result_rows = []

	print((cgmGEN._str_hardBreak))
	for mod in _l_testModules:
		suite = unittest.TestSuite()
		module = "cgm.core.tests.{0}".format(_d_testModulePaths[mod])
		print((">>> Testing Module: {0} | {1}".format(mod,module) + '-'*100))		
		try:
			# importlib.reload leaves removed Test* classes on the module.
			# Drop and reimport so the suite matches the file on disk.
			if module in sys.modules:
				del sys.modules[module]
			importlib.import_module(module)
		except Exception as err:
			log.error("Import fail: {0}".format(module))
			for arg in err.args:
				log.error(arg)
			raise err


		tests = unittest.defaultTestLoader.loadTestsFromName(module)
		
		suite.addTest( tests)		
		
		print_suite(suite)
		
		if testCheck is not True:
			sceneSetup()
			result = unittest.TextTestRunner(verbosity=v).run(suite)
			_tests_run += result.testsRun
			_n_fail += len(result.failures)
			_n_error += len(result.errors)
			_n_skip += len(getattr(result, 'skipped', []))
			_l_result_rows.extend(_collect_result_rows(mod, result))
		
		_len_all += tests.countTestCases()

		"""
		#print("Tests...")
		for t in tests:
			print(("Test: {}".format(t) + '.'*100))		
			
			for t2 in t:
				if v == 1:
					_class = t2.__class__.__name__.split('Test_')[-1]
					_test = t2._testMethodName.split('test_')[-1]
					print(( "    > " + "{0} | {1}".format(_class,_test) ))
				_len_all += 1
				"""
				
		#print(cgmGEN._str_subLine)
		if testCheck is not True:
			print(("<<< Module complete : {0} | {1} ...".format(mod,format(module))))		

	if testCheck is not True:
		print(("Completed [{0}] tests in [{1}] modules >> Time >> = {2} seconds".format(_len_all, len(_l_testModules), "%0.3f"%(time.time()-_t_start)))) 
		cgmGEN.report_enviornmentSingleLine()
		_print_run_summary(_tests_run, len(_l_testModules), time.time()-_t_start,
		                   _n_fail, _n_error, _n_skip, _l_result_rows)
	else:
		print(("Found [{0}] tests in [{1}] modules >> Test check mode. No tests run".format(_len_all, len(_l_testModules))))
		print((cgmGEN._str_hardBreak))






"""def ut_cgmLibraries(*args, **kws):
    class fncWrap(cgmGeneral.cgmFuncCls):
        '''
        Batch tester for cgm core library of functions
        '''
        def __init__(self,*args, **kws):
            super(fncWrap, self).__init__(*args, **kws)
            self._str_funcName = 'ut_cgmLibraries'	
            self._b_autoProgressBar = 1
            self._b_reportTimes = 1
            self.__dataBind__(*args, **kws)
            self.l_funcSteps = [{'step':'validateArgs','call':test_validateArgs.main},
                                ]
    return fncWrap(*args, **kws).go()"""

