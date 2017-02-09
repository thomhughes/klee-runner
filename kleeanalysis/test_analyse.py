# vim: set sw=4 ts=4 softtabstop=4 expandtab:
import os
import logging
import unittest

from . import analyse
from .analyse import KleeResultCorrect, KleeResultUnknown, KleeResultIncorrect, KleeResultMatchSpec, KleeResultMismatchSpec, KleeResultUnknownMatchSpec, KleeResultUnknownReason, KleeMatchSpecReason, KleeMatchSpecWarnings
from . import verificationtasks
from .kleedir import KleeDir
from .kleedir.test import ErrorFile, Early

class MockKleeDir(KleeDir):
    def __init__(self, path, is_valid=True):
        # Don't call super init so we don't
        # do normal initialisation. However
        # by inheriting from `KleeDir` we get all of
        # its property accessors.
        self.path = path
        self.info = None
        self.tests = []
        self._is_valid = is_valid

    def add_test(self, t):
        assert isinstance(t, MockTest)
        lenBefore = len(self.tests)
        self.tests.append(t)
        assert len(self.tests) == lenBefore + 1

    @property
    def is_valid(self):
        return self._is_valid

class MockTest:
    def __init__(self, type, data):
        # FIXME: Test's API needs cleaning up
        assert isinstance(type, str)
        self.ktest_file = '/path/to/fake/test000001.ktest'
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

        if type == 'successful_termination':
            self.is_successful_termination = True
            return

        if type == 'early':
            self.is_successful_termination = False
            assert isinstance(data, Early)
            self.early = data
            return

        self.error = data
        self.is_successful_termination = False
        if type == 'no_assert_fail':
            self.assertion = data
        elif type == 'no_reach_error_function':
            self.abort = data
        elif type == 'no_invalid_free':
            self.free = data
        elif type == 'no_invalid_deref':
            self.ptr = data
        elif type == 'no_integer_division_by_zero':
            self.division = data
        elif type == 'no_overshift':
            self.overshift = data
        elif type == 'user':
            self.user_error = data
        else:
            raise Exception('Unhandled error type')

    def __str__(self):
        return "MockTest: {}".format(self._debug_str)

class AnalyseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # So we can see debug output
        logging.basicConfig(level=logging.DEBUG)

        # Setup the source for task to cex map
        cls.task_to_cex_map_fn = verificationtasks.get_cex_test_cases_for_fp_bench_task
        cls.tasks = verificationtasks.fp_bench_tasks
        assert len(cls.tasks) > 1

    def get_verification_result(self, task, klee_dir, allow_invalid_klee_dir=False):
        return analyse.get_klee_verification_result(
            task,
            klee_dir,
            self.__class__.task_to_cex_map_fn,
            allow_invalid_klee_dir)

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
            "exhaustive_counter_examples": True,
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

        # Check that we get unknown with a klee dir that has no tests
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultUnknown)

        # Add appropriate fake errors that correspond to the counter examples
        taskToTestMap = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            mock_klee_dir.add_test(mockTest)
            taskToTestMap[task] = mockTest

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)


        # Check we observe the expected verification failures
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultIncorrect)
            # Check correct test
            expectedTest = taskToTestMap[result.task]
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(expectedTest, result.test_cases[0])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(0, len(spec_result.warnings))
            self.assertEqual(1, len(spec_result.test_cases))
            self.assertIs(taskToTestMap[t], spec_result.test_cases[0])

    def testExpectedCorrectNoCounterExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
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

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check we observe the expected verification successes
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultCorrect)
            # Check correct tests
            self.assertEqual(5, len(result.test_cases))
            for test_case in result.test_cases:
                self.assertTrue(test_case in mock_klee_dir.successful_terminations)

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMatchSpec)
            self.assertTrue(spec_result.expect_correct)
            self.assertEqual(0, len(spec_result.warnings))
            self.assertEqual(5, len(spec_result.test_cases))
            for test_case in spec_result.test_cases:
                self.assertTrue(test_case in mock_klee_dir.successful_terminations)

    def testUnknownCorrectness(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": None,
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

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check we observe the expected verification successes
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultCorrect)
            # Check correct tests
            self.assertEqual(5, len(result.test_cases))
            for test_case in result.test_cases:
                self.assertTrue(test_case in mock_klee_dir.successful_terminations)

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultUnknownMatchSpec)
            self.assertEqual(None, spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.SPEC_PROVIDES_NO_CORRECTNESS
            )

    def testExpectedCorrectNoCounterExamplesButWithEarlyTerminations(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
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

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Add an early termination. This implies the benchmark was not fully
        # verified.
        mock_klee_dir.add_test(MockTest('early', Early('Fake early termination')))

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 1)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultUnknown)
            self.assertEqual(result.reason, KleeResultUnknownReason.EARLY_TERMINATION)
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(result.test_cases[0], list(mock_klee_dir.early_terminations)[0])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultUnknownMatchSpec)
            self.assertTrue(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.KLEE_COULD_NOT_DETERMINE_CORRECTNESS)

    def testExpectedCorrectNoCounterExamplesButWithUserErrors(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
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

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Add user error. This implies the benchmark was not fully
        # verified.
        ef = ErrorFile(
            'message',
            os.path.join('/some/fake/path', errorFile),
            errorLine + 1,
            0,
            "no stack trace")
        mock_klee_dir.add_test(MockTest('user', ef))

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 1)


        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultUnknown)
            self.assertEqual(result.reason, KleeResultUnknownReason.CEX_BLOCK_TASK)
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(result.test_cases[0], list(mock_klee_dir.user_errors)[0])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultUnknownMatchSpec)
            self.assertTrue(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.KLEE_COULD_NOT_DETERMINE_CORRECTNESS)

    def testMixedCorrectnessNoUB(self):
        mock_klee_dir = MockKleeDir('/fake/path')

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Add error. This implies the benchmark was not fully
        # verified.
        ef = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            1,
            0,
            "no stack trace")
        abortTest = MockTest('no_reach_error_function', ef)
        mock_klee_dir.add_test(abortTest)
        ef2 = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            2,
            0,
            "no stack trace")
        assertTest = MockTest('no_assert_fail', ef2)
        mock_klee_dir.add_test(assertTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            if t == 'no_reach_error_function':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], abortTest)
            elif t == 'no_assert_fail':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], assertTest)
            else:
                # All other tasks classify as correct. `assert()`
                # and `abort()` are terminating so there are cannot
                # be bugs past them.
                self.assertIsInstance(result, KleeResultCorrect)
                self.assertEqual(7, len(result.test_cases))
                expected_test_cases = ( list(mock_klee_dir.successful_terminations) +
                    list(mock_klee_dir.abort_errors) +
                    list(mock_klee_dir.assertion_errors) )
                self.assertEqual(len(expected_test_cases), len(result.test_cases))
                for test_case in result.test_cases:
                    self.assertIn(test_case, expected_test_cases)

    def testMixedCorrectnessNoUBButMissingTerminations(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        # No successful terminations

        # Add error. This implies the benchmark was not fully
        # verified.
        ef = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            1,
            0,
            "no stack trace")
        abortTest = MockTest('no_reach_error_function', ef)
        mock_klee_dir.add_test(abortTest)
        ef2 = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            2,
            0,
            "no stack trace")
        assertTest = MockTest('no_assert_fail', ef2)
        mock_klee_dir.add_test(assertTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            if t == 'no_reach_error_function':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], abortTest)
            elif t == 'no_assert_fail':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], assertTest)
            else:
                # All other tasks classify as correct even
                # though were no succesful terminations the
                # test cases we did observe are terminating which
                # means that for these verification tasks
                # counter examples to those cannot be observed
                self.assertIsInstance(result, KleeResultCorrect)
                self.assertEqual(2, len(result.test_cases))
                self.assertIn(assertTest, result.test_cases)
                self.assertIn(abortTest, result.test_cases)

    def testMixedCorrectnessNoUBWithEarlyTermination(self):
        mock_klee_dir = MockKleeDir('/fake/path')

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Add error. This implies the benchmark was not fully
        # verified.
        ef = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            1,
            0,
            "no stack trace")
        abortTest = MockTest('no_reach_error_function', ef)
        mock_klee_dir.add_test(abortTest)
        ef2 = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            2,
            0,
            "no stack trace")
        assertTest = MockTest('no_assert_fail', ef2)
        mock_klee_dir.add_test(assertTest)

        # Add an early termination. This implies the benchmark was not fully
        # verified.
        mock_klee_dir.add_test(MockTest('early', Early('Fake early termination')))

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 1)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            if t == 'no_reach_error_function':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], abortTest)
            elif t == 'no_assert_fail':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], assertTest)
            else:
                # All other tasks classify as unknown
                self.assertIsInstance(result, KleeResultUnknown)
                self.assertEqual(
                    result.reason,
                    KleeResultUnknownReason.EARLY_TERMINATION
                )
                self.assertEqual(1, len(result.test_cases))
                self.assertEqual(
                    list(mock_klee_dir.early_terminations),
                    result.test_cases
                )

    def testMixedCorrectnessUB(self):
        mock_klee_dir = MockKleeDir('/fake/path')

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Add error. This implies the benchmark was not fully
        # verified.
        ef = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            1,
            0,
            "no stack trace")
        abortTest = MockTest('no_reach_error_function', ef)
        mock_klee_dir.add_test(abortTest)
        # Undefined behaviour (UB): This should block other properties from
        # being verified as correct because execution could continue
        # past it and there could be more bugs there.
        ef2 = ErrorFile(
            'message',
            os.path.join('/some/fake/path', 'dummy.c'),
            2,
            0,
            "no stack trace")
        overshiftTest = MockTest('no_overshift', ef2)
        mock_klee_dir.add_test(overshiftTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 1)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            if t == 'no_reach_error_function':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], abortTest)
            elif t == 'no_overshift':
                self.assertIsInstance(result, KleeResultIncorrect)
                self.assertEqual(1, len(result.test_cases))
                self.assertIs(result.test_cases[0], overshiftTest)
            else:
                # All other tasks classify as unknown
                self.assertIsInstance(result, KleeResultUnknown)
                self.assertEqual(
                    result.reason,
                    KleeResultUnknownReason.CEX_BLOCK_TASK)
                self.assertEqual(1, len(result.test_cases))
                self.assertIn(overshiftTest, result.test_cases)

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
            "exhaustive_counter_examples": True
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

        # Add appropriate fake errors that correspond to the counter examples
        # but with the wrong line number
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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultIncorrect)
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(result.test_cases[0], task_to_test_map[t])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMismatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.DISALLOWED_CEX)
            self.assertTrue(1, len(spec_result.test_cases))
            self.assertIs(task_to_test_map[t], spec_result.test_cases[0])

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
            "exhaustive_counter_examples": True
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

        # Add appropriate fake errors that correspond to the counter examples
        # but with the wrong file name
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', 'different_file.c'),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultIncorrect)
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(result.test_cases[0], task_to_test_map[t])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMismatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.DISALLOWED_CEX)
            self.assertTrue(1, len(spec_result.test_cases))
            self.assertIs(task_to_test_map[t], spec_result.test_cases[0])


    def testExpectedFailureButNoCounterExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            # Note: No counter examples here
            "exhaustive_counter_examples": True
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

        correctness_non_exhaustive_cex = {
            "correct": False,
            # Note: No counter examples here
            "exhaustive_counter_examples": False
        }
        mock_spec_with_non_exhaustive_cex = {
            'verification_tasks': {
                "no_assert_fail": correctness_non_exhaustive_cex,
                "no_reach_error_function": correctness_non_exhaustive_cex,
                "no_invalid_free": correctness_non_exhaustive_cex,
                "no_invalid_deref": correctness_non_exhaustive_cex,
                "no_integer_division_by_zero": correctness_non_exhaustive_cex,
                "no_overshift": correctness_non_exhaustive_cex,
            }
        }

        # Add appropriate fake errors
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultIncorrect)
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(result.test_cases[0], task_to_test_map[t])

            # Now compare against spec where exhaustive_counter_examples is False
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec_with_non_exhaustive_cex
            )
            self.assertIsInstance(spec_result, KleeResultMatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(1, len(spec_result.warnings))
            warning_msg = spec_result.warnings[0][0]
            warning_test_cases = spec_result.warnings[0][1]
            self.assertEqual(
                warning_msg,
                KleeMatchSpecWarnings.CEX_NOT_IN_SPEC)
            self.assertEqual(1, len(warning_test_cases))
            self.assertIs(warning_test_cases[0], task_to_test_map[t])

            # Should we test this? This isn't actually a valid spec!
            # Now compare against spec where exhaustive_counter_examples is True
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMismatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.DISALLOWED_CEX)

    def testExpectedCorrectButHaveExamples(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
            # Note: No counter examples here
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

        # Add appropriate fake errors
        task_to_test_map = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            task_to_test_map[task] = mockTest
            mock_klee_dir.add_test(mockTest)

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultIncorrect)
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(result.test_cases[0], task_to_test_map[t])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMismatchSpec)
            self.assertTrue(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.EXPECT_CORRECT_KLEE_REPORTS_INCORRECT)
            self.assertEqual(1, len(spec_result.test_cases))
            self.assertIs(spec_result.test_cases[0], task_to_test_map[t])

    def testExpectedIncorrectButAppearsCorrect(self):
        mock_klee_dir = MockKleeDir('/fake/path')
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": False,
            "exhaustive_counter_examples": False
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

        successful_terminations = []
        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)
            successful_terminations.append(mockTest)
        self.assertEqual(len(successful_terminations), 5)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check the verification result
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultCorrect)
            self.assertEqual(5, len(result.test_cases))

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMismatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(
                spec_result.reason,
                KleeMatchSpecReason.EXPECT_INCORRECT_KLEE_REPORTS_CORRECT)
            self.assertEqual(5, len(spec_result.test_cases))
            import sys
            for index,t in enumerate(spec_result.test_cases):
                self.assertIs(t, successful_terminations[index])

    def testNoCounterExamplesInvalidKleeDir(self):
        mock_klee_dir = MockKleeDir('/fake/path', is_valid=False)
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
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

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check we observe the expected verification successes
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir)
            self.assertIsInstance(result, KleeResultUnknown)
            self.assertEqual(result.reason, analyse.KleeResultUnknownReason.INVALID_KLEE_DIR)

    def testNoCounterExamplesInvalidKleeDirAllowInvalid(self):
        mock_klee_dir = MockKleeDir('/fake/path', is_valid=False)
        errorFile = "file.c"
        errorLine = 1
        correctness = {
            "correct": True,
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

        # Add fake successful terminations
        for _ in range(0,5):
            mockTest = MockTest('successful_termination', None)
            mock_klee_dir.add_test(mockTest)

        # Check there are no expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 5)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)

        # Check we observe the expected verification successes
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultUnknown)
            self.assertEqual(result.reason, analyse.KleeResultUnknownReason.INVALID_KLEE_DIR)

    def testExpectedCounterExamplesInvalidKleeDirInvalidNotAllowed(self):
        mock_klee_dir = MockKleeDir('/fake/path', is_valid=False)
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
            "exhaustive_counter_examples": True,
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

        # Check that we get unknown with a klee dir that has no tests
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=False)
            self.assertIsInstance(result, KleeResultUnknown)

        # Add appropriate fake errors that correspond to the counter examples
        taskToTestMap = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            mock_klee_dir.add_test(mockTest)
            taskToTestMap[task] = mockTest

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)


        # Check we observe the expected verification failures
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=False)
            self.assertIsInstance(result, KleeResultUnknown)
            self.assertEqual(result.reason, analyse.KleeResultUnknownReason.INVALID_KLEE_DIR)

    def testExpectedCounterExamplesInvalidKleeDirInvalidAllowed(self):
        mock_klee_dir = MockKleeDir('/fake/path', is_valid=False)
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
            "exhaustive_counter_examples": True,
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

        # Check that we get unknown with a klee dir that has no tests
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultUnknown)

        # Add appropriate fake errors that correspond to the counter examples
        taskToTestMap = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            mock_klee_dir.add_test(mockTest)
            taskToTestMap[task] = mockTest

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)


        # Check we observe the expected verification failures
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultIncorrect)
            # Check correct test
            expectedTest = taskToTestMap[result.task]
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(expectedTest, result.test_cases[0])

    def testNotAllExpectedCounterExamplesObserved(self):
        mock_klee_dir = MockKleeDir('/fake/path', is_valid=True)
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
                        {
                            "file": errorFile,
                            "line": errorLine +1,
                        },
                    ]
                },
            ],
            "exhaustive_counter_examples": True,
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

        # Check that we get unknown with a klee dir that has no tests
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultUnknown)

        # Add appropriate fake errors that correspond to one of the counter examples.
        # Note we don't add one of the counter examples
        taskToTestMap = dict()
        for task in mock_spec['verification_tasks'].keys():
            ef = ErrorFile(
                'message',
                os.path.join('/some/fake/path', errorFile),
                errorLine,
                0,
                "no stack trace")
            mockTest = MockTest(task, ef)
            mock_klee_dir.add_test(mockTest)
            taskToTestMap[task] = mockTest

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
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)


        # Check we observe the expected verification failures
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultIncorrect)
            # Check correct test
            expectedTest = taskToTestMap[result.task]
            self.assertEqual(1, len(result.test_cases))
            self.assertIs(expectedTest, result.test_cases[0])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMatchSpec)
            self.assertFalse(spec_result.expect_correct)
            self.assertEqual(
                1,
                len(spec_result.warnings)
            )
            warning_msg, data = spec_result.warnings[0]
            self.assertEqual(
                warning_msg,
                analyse.KleeMatchSpecWarnings.NOT_ALL_CEX_OBSERVED)
            self.assertEqual(
                {'file.c': {2}},
                data
            )
            self.assertEqual(1, len(spec_result.test_cases))

    def testAllExpectedCounterExamplesObserved(self):
        mock_klee_dir = MockKleeDir('/fake/path', is_valid=True)
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
                        {
                            "file": errorFile,
                            "line": errorLine +1,
                        },
                    ]
                },
            ],
            "exhaustive_counter_examples": True,
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

        # Check that we get unknown with a klee dir that has no tests
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultUnknown)

        # Add appropriate fake errors that correspond to one of the counter examples.
        # Note we don't add one of the counter examples
        taskToTestMap = dict()
        for task in mock_spec['verification_tasks'].keys():
            for lineOffset in [ 0, 1]:
                ef = ErrorFile(
                    'message',
                    os.path.join('/some/fake/path', errorFile),
                    errorLine + lineOffset,
                    0,
                    "no stack trace")
                mockTest = MockTest(task, ef)
                mock_klee_dir.add_test(mockTest)
                try:
                    s = taskToTestMap[task]
                except KeyError:
                    s = []
                    taskToTestMap[task] = s
                s.append(mockTest)

        # Check the expected failures are present
        self.assertEqual(len(list(mock_klee_dir.assertion_errors)), 2)
        self.assertEqual(len(list(mock_klee_dir.abort_errors)), 2)
        self.assertEqual(len(list(mock_klee_dir.free_errors)), 2)
        self.assertEqual(len(list(mock_klee_dir.ptr_errors)), 2)
        self.assertEqual(len(list(mock_klee_dir.division_errors)), 2)
        self.assertEqual(len(list(mock_klee_dir.overshift_errors)), 2)
        self.assertEqual(len(list(mock_klee_dir.misc_errors)), 0)
        self.assertEqual(len(list(mock_klee_dir.successful_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.early_terminations)), 0)
        self.assertEqual(len(list(mock_klee_dir.user_errors)), 0)


        # Check we observe the expected verification failures
        for t in self.tasks:
            result = self.get_verification_result(t, mock_klee_dir, allow_invalid_klee_dir=True)
            self.assertIsInstance(result, KleeResultIncorrect)
            # Check correct test
            expectedTests = taskToTestMap[result.task]
            self.assertEqual(2, len(result.test_cases))
            self.assertIs(expectedTests[0], result.test_cases[0])
            self.assertIs(expectedTests[1], result.test_cases[1])

            # Now compare against spec
            spec_result = analyse.match_klee_verification_result_against_spec(
                result,
                mock_spec
            )
            self.assertIsInstance(spec_result, KleeResultMatchSpec)
            self.assertFalse(spec_result.expect_correct)
            # There should be no warnings
            self.assertEqual(
                0,
                len(spec_result.warnings)
            )
            self.assertEqual(2, len(spec_result.test_cases))
