#!/usr/bin/env python3
"""Build a reading PDF from a book's actual manuscript rows, never its raw notes."""

import argparse
from dataclasses import dataclass
from datetime import datetime
from html import escape
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

import pdfplumber
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib import textsplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph
from reportlab.platypus import paragraph as paragraph_module

CHINESE_CLOSING = textsplit.ALL_CANNOT_START + '，。？！；：、）》】」』”’％…'
CHINESE_OPENING = textsplit.ALL_CANNOT_END


class ChineseParagraph(Paragraph):
    """Keep punctuation groups and citation markers attached when wrapping CJK."""

    def breakLinesCJK(self, maxWidths):
        if getattr(self, '_splitpara', False) and hasattr(self, 'blPara'):
            return self.blPara
        if not isinstance(maxWidths, (list, tuple)):
            maxWidths = [maxWidths]
        units = [paragraph_module.cjkU(char, frag, 'utf8')
                 for frag in self.frags for char in getattr(frag, 'text', '')]
        lines, start = [], 0
        while start < len(units):
            limit = maxWidths[min(len(lines), len(maxWidths) - 1)]
            end, used = start, 0
            while end < len(units) and used + units[end].width <= limit + .001:
                used += units[end].width
                end += 1
            if end == start:
                raise ValueError('页面文字区域过窄。')
            if end < len(units):
                candidate = end
                while candidate > start + 1 and (
                    units[candidate] in CHINESE_CLOSING
                    or getattr(units[candidate].frag, 'rise', 0) > 0
                    or units[candidate - 1] in CHINESE_OPENING
                ):
                    candidate -= 1
                # Latin words such as ChatGPT and StreetVoice stay together.
                def latin(char):
                    return char.isascii() and char.isalnum()
                if candidate < len(units) and latin(units[candidate]) and latin(units[candidate - 1]):
                    word_start = candidate
                    while word_start > start and latin(units[word_start - 1]):
                        word_start -= 1
                    if word_start > start:
                        candidate = word_start
                end = candidate
            segment = units[start:end]
            used = sum(unit.width for unit in segment)
            lines.append(paragraph_module.makeCJKParaLine(segment, limit, used, limit - used, False, False))
            start = end
        return paragraph_module.ParaLines(kind=1, lines=lines)


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, check=True)
    return result.stdout.decode('utf-8').strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def roman(number):
    result = ''
    for value, letters in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'),
                           (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'),
                           (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')):
        count, number = divmod(number, value)
        result += letters * count
    return result


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        temp = Path(stream.name)
    os.replace(temp, path)


class Inputs:
    def __init__(self, repo, revision):
        self.repo, self.revision, self.hashes = repo, revision, {}

    def read(self, relative):
        relative = str(PurePosixPath(relative))
        if PurePosixPath(relative).is_absolute() or '..' in PurePosixPath(relative).parts:
            raise ValueError(f'输入路径必须在项目内：{relative}')
        if self.revision:
            result = subprocess.run(['git', '-C', str(self.repo), 'show', f'{self.revision}:{relative}'],
                                    capture_output=True)
            if result.returncode:
                raise ValueError(f'提交中缺少输入文件：{relative}')
            data = result.stdout
        else:
            path = (self.repo / relative).resolve()
            path.relative_to(self.repo)
            data = path.read_bytes()
        self.hashes[relative] = digest(data)
        return data

    def text(self, relative):
        return self.read(relative).decode('utf-8')


def collect_chapters(inputs, book, toc_path):
    toc = inputs.text((book / toc_path).as_posix())
    section = re.search(r'^## 篇目清单\s*\n(.*?)(?=^## |\Z)', toc, re.M | re.S)
    if not section:
        raise ValueError('目录中找不到“篇目清单”，无法确定收录范围。')
    chapters, seen = [], set()
    for line in section.group(1).splitlines():
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) < 3 or cells[2] not in {'初稿', '修改中', '暂定稿'}:
            continue
        # Withdrawal is separate from manuscript maturity in this book's TOC.
        if cells[0] == '—' and any('暂时撤下' in cell for cell in cells[3:]):
            continue
        match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', cells[1])
        if not match:
            raise ValueError(f'已有正文的目录行缺少有效链接：{line}')
        title, target = match.groups()
        target_path = (inputs.repo / book / Path(toc_path).parent / target).resolve()
        relative = target_path.relative_to(inputs.repo)
        target_path.relative_to((inputs.repo / book / '02-正文').resolve())
        if relative.as_posix() in seen:
            raise ValueError(f'目录重复收录：{title}')
        seen.add(relative.as_posix())
        text = inputs.text(relative.as_posix()).strip()
        chunks = re.split(r'\n\s*\n', text)
        if not chunks or chunks[0].strip() != '# ' + title:
            raise ValueError(f'正文标题与目录不一致：{relative}')
        notes, paragraphs = {}, []
        for chunk in chunks[1:]:
            note = re.fullmatch(r'\[\^([^\]]+)\]:\s*(.*)', chunk, re.S)
            if note:
                if note[1] in notes:
                    raise ValueError(f'重复脚注：{note[1]}')
                notes[note[1]] = note[2].replace('\n', ' ')
            elif re.match(r'\s*(?:```|\||!\[|[-*] |\d+\. |>)', chunk):
                raise ValueError(f'{title} 有尚未支持的复杂 Markdown，请先扩展排版器，不能静默省略。')
            else:
                paragraphs.append(chunk.replace('\n', ' '))
        if not paragraphs:
            raise ValueError(f'正文为空：{title}')
        referenced = list(dict.fromkeys(re.findall(r'\[\^([^\]]+)\]', '\n'.join(paragraphs))))
        if set(referenced) != set(notes):
            raise ValueError(f'脚注引用与定义不一致：{title}')
        chapters.append({'title': title, 'path': relative.as_posix(), 'paragraphs': paragraphs,
                         'notes': notes, 'numbers': {key: index + 1 for index, key in enumerate(referenced)}})
    if not chapters:
        raise ValueError('尚无可收录的正文；不会把素材或模板排成书。')
    return chapters


def inline(text, numbers):
    text = escape(text, quote=True)
    text = re.sub(r'\[\^([^\]]+)\]',
                  lambda m: f'<super><font size="7">{numbers[m[1]]}</font></super>', text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<link href="\2" color="#66513c">\1</link>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    return text


def plain(text, numbers):
    text = re.sub(r'^#{2,3}\s*', '', text)
    text = re.sub(r'\[\^([^\]]+)\]', lambda m: str(numbers[m[1]]), text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'\1', text)
    return text.replace('**', '')


@dataclass
class Block:
    paragraph: Paragraph
    expected: str
    height: float


def make_layout(chapters, width, height, margin, body_size):
    content_width = width - 2 * margin
    body = ParagraphStyle('Body', fontName='BookBody', fontSize=body_size,
                          leading=body_size * 1.72, firstLineIndent=body_size * 2,
                          alignment=TA_JUSTIFY, wordWrap='CJK', textColor=colors.HexColor('#302d29'),
                          allowWidows=0, allowOrphans=0)
    subhead = ParagraphStyle('Subhead', parent=body, fontName='BookHeading', fontSize=12,
                             leading=21, firstLineIndent=0, alignment=0)
    note_style = ParagraphStyle('Note', fontName='BookBody', fontSize=7.6, leading=11.5,
                               textColor=colors.HexColor('#6b6259'), wordWrap='CJK')
    pages = []
    for chapter_index, chapter in enumerate(chapters):
        blocks, notes = [], []
        for text in chapter['paragraphs']:
            heading = bool(re.match(r'^#{2,3} ', text))
            markup = inline(re.sub(r'^#{2,3} ', '', text), chapter['numbers'])
            para = ChineseParagraph(markup, subhead if heading else body)
            _, block_height = para.wrap(content_width, 10000)
            blocks.append(Block(para, plain(text, chapter['numbers']), block_height))
        for key, number in chapter['numbers'].items():
            text = f'[{number}] ' + chapter['notes'][key]
            para = ChineseParagraph(inline(text, {}), note_style)
            _, block_height = para.wrap(content_width, 10000)
            notes.append(Block(para, plain(text, {}), block_height))
        note_height = sum(block.height for block in notes) + (13 if notes else 0)
        if note_height > height / 3:
            raise ValueError('本章注释过长，需要调整章末注版式后再导出。')

        def new_page():
            first = not any(p['chapter_index'] == chapter_index for p in pages)
            page = {'chapter_index': chapter_index, 'first': first, 'blocks': [], 'notes': []}
            pages.append(page)
            return page, height - (147 if first else 58)

        page, y = new_page()
        for index, block in enumerate(blocks):
            remaining = sum(b.height + 6 for b in blocks[index:]) + note_height
            # Keep the short closing section and its citation on the same page.
            if index >= len(blocks) - 3 and notes and remaining <= height - 112 and remaining > y - 54:
                if page['blocks']:
                    page, y = new_page()
            if block.height <= y - 54:
                page['blocks'].append((block, y))
                y -= block.height + 6
                continue
            if block.height <= height - 112:
                page, y = new_page()
                page['blocks'].append((block, y))
                y -= block.height + 6
                continue
            # Long paragraphs may span pages; keep ReportLab's orphan protection.
            pending = block.paragraph
            while pending:
                parts = pending.split(content_width, y - 54)
                if not parts:
                    page, y = new_page()
                    parts = pending.split(content_width, y - 54)
                if not parts:
                    raise ValueError('段落无法放入页面，请检查字号或内容。')
                part = parts[0]
                _, part_height = part.wrap(content_width, y - 54)
                page['blocks'].append((Block(part, '', part_height), y))
                y -= part_height + 6
                pending = parts[1] if len(parts) > 1 else None
                if pending:
                    page, y = new_page()
        if notes:
            if y < 54 + note_height:
                raise ValueError('章末注与正文重叠，需要调整排版。')
            page['notes'] = notes
    return pages, content_width


def render(path, config, chapters, cover, edition_date):
    width, height = (value * mm for value in config['page_mm'])
    margin = config['margin_mm'] * mm
    for name, key in [('BookBody', 'regular'), ('BookHeading', 'bold')]:
        font = config['fonts'][key]
        pdfmetrics.registerFont(TTFont(name, os.path.expanduser(font['path']),
                                      subfontIndex=font.get('index', 0)))
    pdfmetrics.registerFontFamily('BookBody', normal='BookBody', bold='BookHeading',
                                  italic='BookBody', boldItalic='BookHeading')
    all_text = config['title'] + config['dedication'] + '目录第一章节个人阅读本年月'
    all_text += ''.join(c['title'] + ''.join(c['paragraphs']) + ''.join(c['notes'].values()) for c in chapters)
    missing = {c for c in all_text if not c.isspace() and ord(c) not in pdfmetrics.getFont('BookBody').face.charToGlyph}
    if missing:
        raise ValueError('字体缺少字符：' + ''.join(sorted(missing)))
    pages, content_width = make_layout(chapters, width, height, margin, config['body_pt'])
    toc_count = max(1, (len(chapters) + 16) // 17)
    body_offset = 2 + toc_count
    chapter_starts = {p['chapter_index']: index + 1 for index, p in enumerate(pages) if p['first']}
    canvas = Canvas(str(path), pagesize=(width, height), pageCompression=1, invariant=0,
                    initialFontName='BookBody', initialFontSize=11, lang='zh-CN')
    canvas.setTitle(config['title'] + ' · 个人阅读版')
    canvas.setAuthor('')
    canvas.setSubject('封面、扉页、目录及当前已有正文')
    canvas.addPageLabel(0, prefix='封面')
    canvas.addPageLabel(1, prefix='扉页')
    canvas.addPageLabel(2, style='ROMAN_LOWER', start=1)
    canvas.addPageLabel(body_offset, style='ARABIC', start=1)
    ink = colors.HexColor('#302d29')
    muted = colors.HexColor('#8a7864')

    def paper():
        canvas.setFillColor(colors.HexColor('#fdfbf7'))
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        canvas.setFillColor(ink)

    def center(text, font_size, y, color=ink, font='BookBody'):
        canvas.setFillColor(color)
        canvas.setFont(font, font_size)
        canvas.drawCentredString(width / 2, y, text)

    canvas.bookmarkPage('cover')
    canvas.addOutlineEntry('封面', 'cover', 0)
    canvas.drawImage(ImageReader(io.BytesIO(cover)), 0, 0, width=width, height=height)
    canvas.showPage()
    paper()
    center(config['title'], 32, height * .64)
    center(config['dedication'], 10.4, height * .64 - 55, muted)
    center('个人阅读本', 9, 88, muted)
    center(edition_date[:4] + '年' + str(int(edition_date[5:7])) + '月', 8, 67, muted)
    canvas.showPage()
    for toc_index in range(toc_count):
        paper()
        if not toc_index:
            canvas.bookmarkPage('contents')
            canvas.addOutlineEntry('目录', 'contents', 0)
        center('目  录', 19, height - 91)
        for row, chapter in enumerate(chapters[toc_index * 17:(toc_index + 1) * 17]):
            chapter_index = toc_index * 17 + row
            y = height - 156 - row * 25
            text = f'{chapter_index + 1:02d}  ' + chapter['title']
            canvas.setFillColor(ink)
            canvas.setFont('BookBody', 11)
            canvas.drawString(margin, y, text)
            text_end = margin + pdfmetrics.stringWidth(text, 'BookBody', 11) + 12
            canvas.setStrokeColor(colors.HexColor('#c6bcae'))
            canvas.setDash(1, 3)
            if text_end < width - margin - 24:
                canvas.line(text_end, y + 3, width - margin - 24, y + 3)
            canvas.setDash()
            canvas.drawRightString(width - margin, y, str(chapter_starts[chapter_index]))
            canvas.linkAbsolute('', f'chapter-{chapter_index}',
                                Rect=(margin, y - 5, width - margin, y + 15), thickness=0)
        center(roman(toc_index + 1), 8.5, 27, muted)
        canvas.showPage()
    regions = []
    for index, page in enumerate(pages):
        paper()
        chapter = chapters[page['chapter_index']]
        if page['first']:
            key = f"chapter-{page['chapter_index']}"
            canvas.bookmarkPage(key)
            canvas.addOutlineEntry(chapter['title'], key, 0)
            center(f"第 {page['chapter_index'] + 1} 章", 9, height - 64, muted)
            center(chapter['title'], 18.5, height - 103, font='BookHeading')
        else:
            canvas.setFont('BookBody', 8)
            canvas.setFillColor(muted)
            canvas.drawString(margin, height - 34, config['title'])
            canvas.drawRightString(width - margin, height - 34, chapter['title'])
        for block, y in page['blocks']:
            block.paragraph.drawOn(canvas, margin, y - block.height)
            regions.append({'page': body_offset + index, 'bbox': [margin - 1, height - y - 1,
                            width - margin + 1, height - y + block.height + 1], 'expected': block.expected})
        if page['notes']:
            total = sum(note.height for note in page['notes'])
            y = 54 + total
            canvas.setStrokeColor(colors.HexColor('#b8aa98'))
            canvas.setLineWidth(.45)
            canvas.line(margin, y + 9, margin + 38, y + 9)
            for block in page['notes']:
                block.paragraph.drawOn(canvas, margin, y - block.height)
                regions.append({'page': body_offset + index, 'bbox': [margin - 1, height - y - 1,
                                width - margin + 1, height - y + block.height + 1], 'expected': block.expected})
                y -= block.height
        center(str(index + 1), 8.5, 27, muted)
        canvas.showPage()
    canvas.save()
    expected_text = ''
    for chapter in chapters:
        expected_text += ''.join(plain(text, chapter['numbers']) for text in chapter['paragraphs'])
        expected_text += ''.join(f'[{number}] ' + plain(chapter['notes'][key], {})
                                 for key, number in chapter['numbers'].items())
    return {'pages': body_offset + len(pages), 'body_offset': body_offset, 'expected_text': expected_text,
            'chapters': [{'title': c['title'], 'path': c['path'], 'page': chapter_starts[i]}
                         for i, c in enumerate(chapters)], 'regions': regions}


def validate_pdf(path, layout, chapters):
    reader = PdfReader(path)
    if len(reader.pages) != layout['pages']:
        raise ValueError('导出页数与排版记录不一致。')
    if reader.page_labels[layout['body_offset']] != '1' or not reader.pages[2].get('/Annots'):
        raise ValueError('目录链接或正文页码缺失。')
    normalize = lambda text: re.sub(r'\s+', '', text or '')
    checked = 0
    extracted = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for char in page.chars:
                if char['x0'] < 0 or char['x1'] > page.width + .1 or char['top'] < 0 or char['bottom'] > page.height + .1:
                    raise ValueError('文字超出页面边界。')
        for region in layout['regions']:
            actual = pdf.pages[region['page']].crop(region['bbox']).extract_text(x_tolerance=1.5, y_tolerance=3)
            extracted.append(actual or '')
            if region['expected'] and normalize(actual) != normalize(region['expected']):
                raise ValueError(f"正文提取核对失败，第 {region['page'] + 1} 页：{actual!r}")
            checked += 1
    if normalize(''.join(extracted)) != normalize(layout['expected_text']):
        raise ValueError('整篇正文与来源不一致，可能有跨页遗漏。')
    return {'text_blocks_checked': checked, 'full_text': 'passed', 'page_bounds': 'passed', 'navigation': 'passed'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--config', required=True)
    parser.add_argument('--mode', choices=['preview', 'merged'], default='preview')
    parser.add_argument('--revision')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--status-file', type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    revision = None
    try:
        if args.mode == 'merged':
            revision = git(repo, 'rev-parse', (args.revision or 'HEAD') + '^{commit}')
        inputs = Inputs(repo, revision)
        config_path = PurePosixPath(args.config)
        config = json.loads(inputs.text(config_path.as_posix()))
        book = config_path.parent.parent
        chapters = collect_chapters(inputs, book, config['toc'])
        cover = inputs.read((book / config['cover']).as_posix())
        output = args.output
        if output is None:
            if args.mode == 'merged':
                output = repo / book / '04-导出/合入版' / f"{config['title']}-{revision[:12]}.pdf"
            else:
                raise ValueError('预览请明确指定 --output，避免覆盖已有阅读样本。')
        output = output.resolve()
        output.relative_to(repo / book / '04-导出')
        output.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = output.with_suffix('.json')
        renderer_hash = digest(Path(__file__).read_bytes())
        if revision and output.exists() and metadata_path.exists():
            prior = json.loads(metadata_path.read_text())
            if (prior.get('source_revision') == revision and prior.get('inputs') == inputs.hashes
                    and prior.get('renderer_sha256') == renderer_hash
                    and prior.get('pdf_sha256') == digest(output.read_bytes())):
                if args.output is None:
                    atomic_json(output.parent / 'latest.json', prior)
                if args.status_file:
                    atomic_json(args.status_file, {'status': 'success', 'source_revision': revision,
                                                  'output': prior['output'], 'reused': True})
                print(f'阅读版已存在：{output}')
                return 0
        edition_date = git(repo, 'show', '-s', '--format=%cs', revision) if revision else datetime.now().date().isoformat()
        scratch = repo / 'tmp/pdfs'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='build-', dir=scratch) as work:
            temporary = Path(work) / 'reading.pdf'
            layout = render(temporary, config, chapters, cover, edition_date)
            checks = validate_pdf(temporary, layout, chapters)
            metadata = {'output': output.relative_to(repo).as_posix(), 'mode': args.mode,
                        'source_revision': revision, 'base_revision': git(repo, 'rev-parse', 'HEAD'),
                        'inputs': inputs.hashes, 'renderer_sha256': renderer_hash,
                        'pdf_sha256': digest(temporary.read_bytes()), 'pages': layout['pages'],
                        'chapters': layout['chapters'], 'checks': checks, 'visual_review': 'pending'}
            os.replace(temporary, output)
            atomic_json(metadata_path, metadata)
        if args.mode == 'merged' and args.output is None:
            atomic_json(output.parent / 'latest.json', metadata)
        if args.status_file:
            atomic_json(args.status_file, {'status': 'success', 'source_revision': revision,
                                          'output': metadata['output'], 'reused': False})
        print(json.dumps({'output': str(output), 'pages': metadata['pages'], 'checks': checks}, ensure_ascii=False))
        return 0
    except Exception as error:
        if args.status_file:
            atomic_json(args.status_file, {'status': 'failed', 'source_revision': revision, 'error': str(error)})
        print(f'阅读版生成失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
