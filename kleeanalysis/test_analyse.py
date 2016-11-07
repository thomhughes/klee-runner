# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import os
import logging
import unittest

from . import analyse
from .kleedir import KleeDir
from .kleedir.test import ErrorFile

class MockKleeDir(KleeDir):
    def __init__(self, path):
        # Don't call super init so we don't
        # do normal initialisation. However
        # by inheriting from `KleeDir` we get all of
        # its property accessors.
        self.path = path
        self.info = None
        self.tests = []

    def add_test(self, t):
        assert isinstance(t, MockTest)
        lenBefore = len(self.tests)
        self.tests.append(t)
        assert len(self.tests) == lenBefore + 1

class MockTest:
    def __init__(self, type, errorFile):
        # FIXME: Test's API needs cleaning up
        assert isinstance(type, str)
        self.path = '/path/to/fake/test000001.ktest'
        self.identifier = 1

        self.error = None
        self.execution_error = None
        self.abort = None
        self.division = None
        self.assertion = None
        self.free = None
        self.ptr = None
        self.overshift = None
        self.readonly_error = None
        self.user_error = None
        self.overflow = None
        self.misc_error = None
        self.early = None

        self._debug_str = type

        self.error = errorFile
        self.is_successful_termination = False
        if type == 'no_assert_fail':
            self.assertion = errorFile
        elif type == 'no_reach_error_function':
            self.abort = errorFile
        elif type == 'no_invalid_free':
            self.free = errorFile
        elif type == 'no_invalid_deref':
            self.ptr = errorFile
        elif type == 'no_integer_division_by_zero':
            self.division = errorFile
        elif type == 'no_overshift':
            self.overshift = errorFile
        else:
            raise Exception('Unhandled error type')

    def __str__(self):
        return "MockTest: {}".format(self._debug_str)

class AnalyseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # So we can see debug output
        logging.basicConfig(level=logging.DEBUG)
        #pass

    def testExpectedCounterExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "counter_examples": [
                {
                    "description": "dummy counterexample",
                    "locations": [
                        {
                            "file": errorFile,
                            "line": errorLine,
                        },
                    ]
                },
            ],
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)

        # Add appropriate fake errors that correspond to the counter examples
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            mock_klee_dir.add_test(mockTest)
            if task == 'no_invalid_deref':
                print("Made mock test: {}".format(mockTest))
                print("mock test :{}".format(mockTest.ptr))

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)

    def testUnExpectedCounterExamplesWrongLine(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "counter_examples": [
                {
                    "description": "dummy counterexample",
                    "locations": [
                        {
                            "file": errorFile,
                            "line": errorLine,
                        },
                    ]
                },
            ],
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)

        # Add appropriate fake errors that correspond to the counter examples
        # but with the wrong line nuymber
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine + 1,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)
            if task == 'no_invalid_deref':
                print("Made mock test: {}".format(mockTest))
                print("mock test :{}".format(mockTest.ptr))

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), len(mock_spec['verification_tasks'].keys()))
        for v in failures:
            self.assertIsInstance(v, analyse.VerificationFailure)
            task = v.task
            taskFailures = v.failures
            self.assertEqual(len(taskFailures), 1)

            # Check it's the task we expect
            expectedFailure = task_to_test_map[task]
            self.assertIs(taskFailures[0], expectedFailure)

    def testUnExpectedCounterExamplesWrongFile(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "counter_examples": [
                {
                    "description": "dummy counterexample",
                    "locations": [
                        {
                            "file": errorFile,
                            "line": errorLine,
                        },
                    ]
                },
            ],
        }
        mock_spec = {
            'verification_tasks': {
                "no_assert_fail": correctness,
                "no_reach_error_function": correctness,
                "no_invalid_free": correctness,
                "no_invalid_deref": correctness,
                "no_integer_division_by_zero": correctness,
                "no_overshift": correctness,
            }
        }

        # Check that we get zero failures with a klee dir that has no tests
        failures = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), 0)

        # Add appropriate fake errors that correspond to the counter examples
        # but with the wrong line nuymber
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', 'different_file.c'),
                errorLine + 1,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)
            if task == 'no_invalid_deref':
                print("Made mock test: {}".format(mockTest))
                print("mock test :{}".format(mockTest.ptr))

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)


        failures = analyse._check_against_spec(mock_spec, mock_klee_dir)
        self.assertIsInstance(failures, list)
        self.assertEqual(len(failures), len(mock_spec['verification_tasks'].keys()))
        for v in failures:
            self.assertIsInstance(v, analyse.VerificationFailure)
            task = v.task
            taskFailures = v.failures
            self.assertEqual(len(taskFailures), 1)

            # Check it's the task we expect
            expectedFailure = task_to_test_map[task]
            self.assertIs(taskFailures[0], expectedFailure)
