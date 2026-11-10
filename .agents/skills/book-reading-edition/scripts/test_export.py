"""Exercise real PDF output and Git integration in disposable repositories."""

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from pypdf import PdfReader
import pdfplumber


PROJECT = Path(__file__).resolve().parents[4]
SKILL = PROJECT / '.agents/skills/book-reading-edition'


class ReadingEditionTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((SKILL / 'scripts/export_book.py').is_file(),
                        'The reusable PDF exporter has not been implemented.')
        self.temp = tempfile.TemporaryDirectory(prefix='book-reading-test-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / 'repository with spaces'
        self.repo.mkdir()
        shutil.copytree(SKILL, self.repo / '.agents/skills/book-reading-edition',
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(PROJECT / '.githooks', self.repo / '.githooks')
        self.book = self.repo / '不要怕'
        for directory in ('02-正文', '03-附件', '00-全书规划', 'specs', '04-导出'):
            (self.book / directory).mkdir(parents=True)
        shutil.copy2(PROJECT / '不要怕/03-附件/封面/不要怕-封面-v0.3.png',
                     self.book / '03-附件/封面.png')
        self.config = '不要怕/specs/reading-edition.json'
        config = json.loads((PROJECT / self.config).read_text())
        config['cover'] = '03-附件/封面.png'
        (self.repo / self.config).write_text(json.dumps(config, ensure_ascii=False))
        self.body = self.book / '02-正文/第一篇.md'
        self.body.write_text('# 第一篇\n\n这是已经保存的正文。\n\n还有一句需要留下来的话。[^n]\n\n[^n]: 出处说明。[来源](https://example.com/source)。\n')
        self.toc = self.book / '00-全书规划/全书目录.md'
        self.toc.write_text('# 目录\n\n## 篇目清单\n\n| 阅读顺序 | 篇名与文件链接 | 状态 |\n| --- | --- | --- |\n| 待编排 | [第一篇](../02-正文/第一篇.md) | 初稿 |\n| 待编排 | [待写篇目](../01-素材.md) | 待写 |\n\n## 其他说明\n')
        (self.repo / '.gitignore').write_text('tmp/pdfs/\n**/04-导出/合入版/\n**/__pycache__/\n')
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Reading edition test')
        self.git('config', 'user.email', 'reading-test@example.invalid')
        self.git('add', '.')
        self.git('commit', '-qm', 'Fixture baseline')
        subprocess.run(['bash', str(self.repo / '.agents/skills/book-reading-edition/scripts/install_hooks.sh')],
                       cwd=self.repo, check=True, capture_output=True)

    def git(self, *args, check=True):
        return subprocess.run(['git', *args], cwd=self.repo, check=check,
                              capture_output=True, text=True)

    def export(self, *args, check=True):
        return subprocess.run(['bash', str(self.repo / '.agents/skills/book-reading-edition/scripts/run.sh'),
                               '--repo', str(self.repo), '--config', self.config, *args],
                              cwd=self.repo, check=check, capture_output=True, text=True)

    def latest(self):
        return json.loads((self.book / '04-导出/合入版/latest.json').read_text())

    def test_preview_has_front_matter_links_and_only_written_chapters(self):
        output = self.book / '04-导出/样本.pdf'
        before = self.body.read_bytes()
        self.export('--mode', 'preview', '--output', str(output))
        reader = PdfReader(output)
        text = re.sub(r'\s+', '', ''.join(page.extract_text() or '' for page in reader.pages))
        self.assertGreaterEqual(len(reader.pages), 4)
        self.assertIn('目录', text)
        self.assertIn('这是已经保存的正文', text)
        self.assertIn('出处说明', text)
        self.assertNotIn('待写篇目', text)
        self.assertTrue(reader.pages[2].get('/Annots'))
        self.assertEqual(reader.page_labels[3], '1')
        self.assertEqual(before, self.body.read_bytes())

    def test_committed_export_excludes_uncommitted_manuscript_edits(self):
        self.body.write_text(self.body.read_text() + '\n尚未提交的另一句话。\n')
        output = self.book / '04-导出/已提交版.pdf'
        self.export('--mode', 'merged', '--revision', 'HEAD', '--output', str(output))
        text = ''.join(page.extract_text() or '' for page in PdfReader(output).pages)
        self.assertNotIn('尚未提交', text)
        self.assertIn('这是已经保存的正文', text)

    def test_fast_forward_merge_invokes_export_and_adds_new_chapter(self):
        self.git('switch', '-qc', 'feature')
        (self.book / '02-正文/第二篇.md').write_text('# 第二篇\n\n这是第二篇的内容。\n')
        self.toc.write_text(self.toc.read_text().replace('## 其他说明',
            '| 待编排 | [第二篇](../02-正文/第二篇.md) | 初稿 |\n\n## 其他说明'))
        self.git('add', '.')
        self.git('commit', '-qm', 'Add chapter')
        self.assertFalse((self.book / '04-导出/合入版/latest.json').exists())
        self.git('switch', '-q', 'main')
        self.git('merge', '--ff-only', 'feature')
        latest = self.latest()
        self.assertEqual(latest['source_revision'], self.git('rev-parse', 'HEAD').stdout.strip())
        self.assertEqual(len(latest['chapters']), 2)
        self.assertEqual(self.git('status', '--porcelain').stdout, '')

    def test_squash_waits_for_commit_then_exports(self):
        self.git('switch', '-qc', 'feature')
        self.body.write_text(self.body.read_text().replace('已经保存', '刚刚修订'))
        self.git('add', '.')
        self.git('commit', '-qm', 'Revise chapter')
        self.git('switch', '-q', 'main')
        self.git('merge', '--squash', 'feature')
        self.assertFalse((self.book / '04-导出/合入版/latest.json').exists())
        self.git('commit', '-qm', 'Integrate revision')
        self.assertEqual(self.latest()['source_revision'], self.git('rev-parse', 'HEAD').stdout.strip())

    def test_non_fast_forward_merge_exports_merge_commit(self):
        self.git('switch', '-qc', 'feature')
        self.body.write_text(self.body.read_text().replace('已经保存', '刚刚修订'))
        self.git('add', '.')
        self.git('commit', '-qm', 'Revise chapter')
        self.git('switch', '-q', 'main')
        self.git('merge', '--no-ff', '-m', 'Integrate chapter', 'feature')
        self.assertEqual(len(self.git('rev-list', '--parents', '-n', '1', 'HEAD').stdout.split()), 3)
        self.assertEqual(self.latest()['source_revision'], self.git('rev-parse', 'HEAD').stdout.strip())

    def test_conflicted_merge_waits_until_resolution_commit(self):
        self.git('switch', '-qc', 'feature')
        self.body.write_text('# 第一篇\n\n分支里的新内容。\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Feature revision')
        self.git('switch', '-q', 'main')
        self.body.write_text('# 第一篇\n\n主干里的另一种修改。\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Main revision')
        previous = self.latest()
        result = self.git('merge', 'feature', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(previous, self.latest())
        self.body.write_text('# 第一篇\n\n人工整合后的内容。\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Resolve chapter')
        self.assertEqual(self.latest()['source_revision'], self.git('rev-parse', 'HEAD').stdout.strip())

    def test_long_paragraph_is_preserved_across_pages(self):
        long_text = ''.join(f'这是第{number}次回看的记录，需要完整保留。' for number in range(150))
        self.body.write_text('# 第一篇\n\n' + long_text + '\n')
        output = self.book / '04-导出/长篇.pdf'
        self.export('--mode', 'preview', '--output', str(output))
        with pdfplumber.open(output) as pdf:
            body_pages = [page.crop((45, 140 if index == 0 else 50, page.width - 40, page.height - 45))
                          for index, page in enumerate(pdf.pages[3:])]
            text = re.sub(r'\s+', '', ''.join(page.extract_text() or '' for page in body_pages))
        self.assertEqual(long_text, text)

    def test_rebase_main_exports_final_rewritten_commit(self):
        self.git('switch', '-qc', 'upstream')
        (self.repo / 'upstream-note.txt').write_text('independent change')
        self.git('add', '.')
        self.git('commit', '-qm', 'Upstream change')
        self.git('switch', '-q', 'main')
        self.body.write_text('# 第一篇\n\n主干上的新版正文。\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Book revision')
        previous = self.latest()['source_revision']
        self.git('rebase', 'upstream')
        current = self.git('rev-parse', 'HEAD').stdout.strip()
        self.assertNotEqual(previous, current)
        self.assertEqual(self.latest()['source_revision'], current)

    def test_reorder_rename_and_withdraw_follow_actual_toc(self):
        renamed = self.body.with_name('改名的第一篇.md')
        renamed.write_text(self.body.read_text().replace('# 第一篇', '# 改名的第一篇'))
        self.body.unlink()
        (self.book / '02-正文/第二篇.md').write_text('# 第二篇\n\n新章的内容。\n')
        (self.book / '02-正文/撤下篇.md').write_text('# 撤下篇\n\n不应进入阅读版的文字。\n')
        self.toc.write_text('# 目录\n\n## 篇目清单\n\n| 顺序 | 篇名 | 状态 |\n| --- | --- | --- |\n'
                           '| 1 | [第二篇](../02-正文/第二篇.md) | 初稿 |\n'
                           '| 2 | [改名的第一篇](../02-正文/改名的第一篇.md) | 修改中 |\n'
                           '| - | [撤下篇](../02-正文/撤下篇.md) | 撤下 |\n')
        output = self.book / '04-导出/重排.pdf'
        self.export('--mode', 'preview', '--output', str(output))
        metadata = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual([c['title'] for c in metadata['chapters']], ['第二篇', '改名的第一篇'])
        text = ''.join(p.extract_text() or '' for p in PdfReader(output).pages)
        self.assertNotIn('不应进入', text)
        self.assertLess(metadata['chapters'][0]['page'], metadata['chapters'][1]['page'])

    def test_chinese_closing_punctuation_does_not_start_lines(self):
        self.body.write_text('# 第一篇\n\n' + '甲' * 24 + '，' + '乙' * 26 + '。”[^n]\n\n[^n]: 来源说明。\n')
        output = self.book / '04-导出/标点.pdf'
        self.export('--mode', 'preview', '--output', str(output))
        with pdfplumber.open(output) as pdf:
            for page in pdf.pages[3:]:
                for line in (page.extract_text() or '').splitlines():
                    self.assertNotIn(line.strip()[0], '，。？！；：、）》】」』”’')

    def test_withdrawal_uses_existing_book_convention_without_losing_maturity(self):
        archive = self.book / '99-归档'
        archive.mkdir()
        (archive / '旧篇.md').write_text('# 旧篇\n\n旧篇内容应保留在归档中。\n')
        self.toc.write_text(self.toc.read_text().replace('## 其他说明',
            '| — | [旧篇](../99-归档/旧篇.md) | 初稿 | 旧事 | 暂时撤下 |\n\n## 其他说明'))
        output = self.book / '04-导出/撤下后.pdf'
        self.export('--mode', 'preview', '--output', str(output))
        metadata = json.loads(output.with_suffix('.json').read_text())
        self.assertEqual([c['title'] for c in metadata['chapters']], ['第一篇'])
        self.assertEqual((archive / '旧篇.md').read_text(), '# 旧篇\n\n旧篇内容应保留在归档中。\n')

    def test_failed_export_keeps_last_successful_pdf_and_reports_failure(self):
        self.git('commit', '--allow-empty', '-qm', 'First published snapshot')
        before = self.latest()
        pdf = self.repo / before['output']
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        self.git('rm', str(self.body.relative_to(self.repo)))
        result = self.git('commit', '-qm', 'Missing chapter is an export error')
        self.assertIn('阅读版生成失败', result.stderr)
        self.assertEqual(before, self.latest())
        self.assertEqual(digest, hashlib.sha256(pdf.read_bytes()).hexdigest())
        status = json.loads((self.repo / '.git/book-reading/last-run.json').read_text())
        self.assertEqual(status['status'], 'failed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
