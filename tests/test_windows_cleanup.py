"""Regression checks for Windows PDF handles and failed-job retry.
Run: python -m unittest discover -s tests -v
Set PDF_TEST_INPUT to exercise real PDF conversion as well.
"""
import hashlib,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import converter,batch

class RetryTests(unittest.TestCase):
    def test_previous_failure_retries_and_success_skips(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'input.pdf';source.write_bytes(b'test fixture')
            runner=batch.Runner(Path(td)/'output')
            try:
                with patch.object(batch,'convert',side_effect=PermissionError('WinError 32: body.pdf locked')):
                    self.assertEqual(runner.process(source)['status'],'NEEDS_REVIEW')
                def succeeds(src,dest):
                    Path(dest).write_bytes(b'completed fixture')
                    return {'status':'CONVERTED_REVIEW_LAYOUT','source_pages':1,'output_pages':1,'tables':0}
                with patch.object(batch,'convert',side_effect=succeeds) as convert:
                    self.assertEqual(runner.process(source)['status'],'CONVERTED_REVIEW_LAYOUT')
                    self.assertEqual(runner.process(source)['status'],'ALREADY_PROCESSED')
                    self.assertEqual(convert.call_count,1)
            finally:runner.close()

@unittest.skipUnless(os.environ.get('PDF_TEST_INPUT'),'Set PDF_TEST_INPUT to a supported source PDF.')
class HandleTests(unittest.TestCase):
    def exercise(self,fail):
        real_open=converter.fitz.open;real_tempdir=tempfile.TemporaryDirectory
        opened=[];self_cleanup_checks=[]
        def tracked_open(*args,**kwargs):
            doc=real_open(*args,**kwargs);opened.append(doc);return doc
        class WindowsLikeDirectory(real_tempdir):
            def __exit__(self,*args):
                for doc in opened:
                    if not doc.is_closed and doc.name and Path(doc.name).parent==Path(self.name):
                        raise AssertionError('Windows would reject cleanup: temporary PDF still open')
                self_cleanup_checks.append(True)
                return super().__exit__(*args)
        with real_tempdir() as td:
            destination=Path(td)/'result.pdf'
            with patch.object(converter.fitz,'open',side_effect=tracked_open),patch.object(converter.tempfile,'TemporaryDirectory',WindowsLikeDirectory):
                if fail:
                    with patch.object(converter,'numeric_rows',side_effect=RuntimeError('injected validation error')):
                        with self.assertRaisesRegex(RuntimeError,'injected validation error'):
                            converter.convert(os.environ['PDF_TEST_INPUT'],destination)
                else:
                    result=converter.convert(os.environ['PDF_TEST_INPUT'],destination)
                    self.assertEqual(result['font_pt'],11)
                    self.assertEqual(result['numeric_rows_verified'],193)
                    self.assertTrue(destination.is_file())
            self.assertTrue(self_cleanup_checks)
            self.assertTrue(all(doc.is_closed for doc in opened),'PDF handles leaked on return/exception')
    def test_success_closes_before_temp_cleanup(self):self.exercise(False)
    def test_failure_closes_before_temp_cleanup(self):self.exercise(True)

if __name__=='__main__':unittest.main()
