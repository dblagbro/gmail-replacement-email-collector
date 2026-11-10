"""The release operator must modify only the named service's exact image line."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).with_name('release.py')
spec=importlib.util.spec_from_file_location('collector_release',path)
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ScopeTests(unittest.TestCase):
    def test_preserve_other_services_comments_and_configuration(self):
        before='services:\n  unrelated:\n    image: other:old\n  gmail-email-collector:\n    image: collector:old\n    mem_limit: 1g\n    environment:\n      PRIVATE_VALUE: placeholder\n  later:\n    image: collector:old\n'
        after=release.patch_image(before,'collector:old','sha256:fixture')
        self.assertEqual(after,before.replace('    image: collector:old','    image: sha256:fixture',1))
    def test_reject_wrong_original_image(self):
        with self.assertRaises(AssertionError):release.patch_image('services:\n  gmail-email-collector:\n    image: changed\n','old','new')
    def test_reject_missing_service(self):
        with self.assertRaises(AssertionError):release.patch_image('services:\n  unrelated:\n    image: old\n','old','new')
    def test_reject_duplicate_service(self):
        block='  gmail-email-collector:\n    image: old\n'
        with self.assertRaises(AssertionError):release.patch_image('services:\n'+block+block,'old','new')
    def test_reject_multiple_image_lines(self):
        with self.assertRaises(AssertionError):release.patch_image('services:\n  gmail-email-collector:\n    image: old\n    image: old\n','old','new')
    def test_end_of_file_service(self):
        self.assertEqual(release.patch_image('services:\n  gmail-email-collector:\n    image: old\n','old','new'),'services:\n  gmail-email-collector:\n    image: new\n')

if __name__=='__main__':unittest.main()
