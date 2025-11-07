# -*- coding: utf-8 -*-
"""
Markdown题库转HTML插件
支持自定义题库格式，生成离线可用的手机刷题HTML文件
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import re
import base64
import mimetypes
from pathlib import Path
from urllib.parse import unquote  # 添加URL解码


class Plugin:
    def __init__(self):
        self.name = "md_qbank_to_html"
        self.display_name = "Markdown题库转HTML"
        self.tooltip = "将Markdown格式题库转换为离线HTML手机刷题文件"

    def execute_gui(self, root, status_text):
        """GUI模式执行"""
        # 选择输入的Markdown文件
        md_file = filedialog.askopenfilename(
            title="选择Markdown题库文件",
            filetypes=[("Markdown文件", "*.md"), ("所有文件", "*.*")]
        )
        if not md_file:
            return
        
        # 选择输出HTML文件路径
        default_name = Path(md_file).stem + "_手机刷题神器.html"
        html_file = filedialog.asksaveasfilename(
            title="保存HTML文件",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("HTML文件", "*.html")]
        )
        if not html_file:
            return
        
        status_text.insert(tk.END, f"开始转换：{Path(md_file).name}\n")
        status_text.see(tk.END)
        root.update_idletasks()
        
        try:
            converter = MarkdownQBankConverter(md_file)
            html_content = converter.convert()
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            stats = converter.get_stats()
            status_text.insert(tk.END, f"✓ 转换成功！\n")
            status_text.insert(tk.END, f"  题库名称：{stats['title']}\n")
            status_text.insert(tk.END, f"  题目总数：{stats['total']}\n")
            for qtype, count in stats['by_type'].items():
                status_text.insert(tk.END, f"  - {qtype}：{count}题\n")
            status_text.insert(tk.END, f"  保存路径：{html_file}\n\n")
            
            messagebox.showinfo("成功", f"题库转换完成！\n共{stats['total']}道题\n可直接在手机浏览器中打开使用")
        except Exception as e:
            err_msg = f"转换失败：{str(e)}\n"
            status_text.insert(tk.END, err_msg)
            messagebox.showerror("错误", err_msg)
        finally:
            status_text.see(tk.END)

    def execute_cli(self, args):
        """CLI模式执行"""
        if len(args) < 1:
            print("用法: md_qbank_to_html <markdown文件> [输出html文件]")
            return
        
        md_file = args[0]
        html_file = args[1] if len(args) > 1 else Path(md_file).stem + "_手机刷题神器.html"
        
        try:
            converter = MarkdownQBankConverter(md_file)
            html_content = converter.convert()
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            stats = converter.get_stats()
            print(f"转换成功！题库：{stats['title']}，共{stats['total']}题")
            print(f"保存至：{html_file}")
        except Exception as e:
            print(f"转换失败：{e}")


class MarkdownQBankConverter:
    """Markdown题库转换器"""
    
    def __init__(self, md_file):
        self.md_file = Path(md_file)
        self.md_dir = self.md_file.parent
        self.title = ""
        self.description = ""
        self.questions = []
        self.stats = {'total': 0, 'by_type': {}}
        
        self._parse()
    
    def _parse(self):
        """解析Markdown文件"""
        with open(self.md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        lines = content.split('\n')
        i = 0
        current_qtype = ""
        
        while i < len(lines):
            line = lines[i].strip()
            
            # 一级标题：题库名称
            if line.startswith('# '):
                self.title = line[2:].strip()
                # 收集说明文字（直到下一个标题）
                i += 1
                desc_lines = []
                while i < len(lines) and not lines[i].strip().startswith('#'):
                    if lines[i].strip():
                        desc_lines.append(lines[i].strip())
                    i += 1
                self.description = '\n'.join(desc_lines)
                continue
            
            # 二级标题：题型
            if line.startswith('## '):
                current_qtype = line[3:].strip().replace('，', '').replace(',', '')
                i += 1
                continue
            
            # 题目（有序列表）
            if re.match(r'^\d+\.\s+', line):
                question = self._parse_question(lines, i, current_qtype)
                if question:
                    self.questions.append(question)
                    self.stats['total'] += 1
                    self.stats['by_type'][current_qtype] = self.stats['by_type'].get(current_qtype, 0) + 1
                # 跳过已处理的行
                i = question.get('end_line', i + 1)
                continue
            
            i += 1
    
    def _parse_question(self, lines, start_idx, qtype):
        """解析单个题目"""
        match = re.match(r'^(\d+)\.\s+(.+)', lines[start_idx].strip())
        if not match:
            return None
        
        qid = match.group(1)
        stem = match.group(2)
        
        # 收集题干（可能跨多行）
        i = start_idx + 1
        stem_lines = [stem]
        
        # 继续读取直到遇到选项（以数字.开头的子列表）
        while i < len(lines):
            line = lines[i].strip()
            # 遇到选项或下一题或标题，停止
            if re.match(r'^\d+\.\s+', line) or line.startswith('#'):
                break
            if line:
                stem_lines.append(line)
            i += 1
        
        stem = '\n'.join(stem_lines)
        
        # 解析选项
        options = []
        while i < len(lines):
            line = lines[i].strip()
            
            # 下一题或新标题，结束
            if re.match(r'^\d+\.\s+', line) and not re.match(r'^\s+\d+\.\s+', lines[i]):
                break
            if line.startswith('#'):
                break
            
            # 选项（缩进的有序列表）
            option_match = re.match(r'^(\d+)\.\s+(.+)', line)
            if option_match and lines[i].startswith((' ', '\t')):
                option_num = option_match.group(1)
                option_text = option_match.group(2)
                
                # 检查是否是正确答案（包含==）
                is_correct = '==' in option_text
                
                # 提取解析（::后面的内容）
                explanation = ""
                if '::' in option_text:
                    parts = option_text.split('::', 1)
                    option_text = parts[0]
                    explanation = parts[1]
                
                # 移除正确答案标记
                option_text = option_text.replace('==', '')
                
                options.append({
                    'num': option_num,
                    'text': option_text.strip(),
                    'is_correct': is_correct,
                    'explanation': explanation.strip()
                })
            
            i += 1
        
        return {
            'id': qid,
            'type': qtype,
            'stem': stem,
            'options': options,
            'end_line': i
        }
    
    def _process_markdown(self, text):
        """处理Markdown内容：公式、图片、代码块等"""
        if not text:
            return ""
        
        # 先处理代码块（避免代码块内的特殊字符被处理）
        code_blocks = []
        def save_code(m):
            code_blocks.append(m.group(0))
            return f"<<<CODE{len(code_blocks)-1}>>>"
        text = re.sub(r'```(\w*)\n(.*?)```', save_code, text, flags=re.DOTALL)
        
        # 保存公式（避免公式内的特殊字符被处理）
        formulas = []
        def save_formula(m):
            formulas.append(m.group(0))
            return f"<<<MATH{len(formulas)-1}>>>"
        
        # 处理块级公式 $$...$$
        text = re.sub(r'\$\$\s*\n?(.*?)\n?\s*\$\$', save_formula, text, flags=re.DOTALL)
        # 处理行内公式 $...$
        text = re.sub(r'\$([^$\n]+)\$', save_formula, text)
        
        # 处理图片
        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            lambda m: self._embed_image(m.group(1), m.group(2)),
            text
        )
        
        # 处理Markdown基本语法
        # 粗体 **text** 或 __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        
        # 斜体 *text* 或 _text_
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
        
        # 行内代码 `code`
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        
        # 处理换行：连续两个换行为段落，单个换行为<br>
        text = text.replace('\n\n', '</p><p>')
        text = text.replace('\n', '<br>')
        text = '<p>' + text + '</p>'
        # 清理多余的空段落
        text = re.sub(r'<p>\s*</p>', '', text)
        
        # 恢复公式
        for i, formula in enumerate(formulas):
            placeholder = f"<<<MATH{i}>>>"
            # 判断是块级还是行内公式
            if formula.startswith('$$'):
                text = text.replace(placeholder, f'<div class="math-block">{formula}</div>')
            else:
                text = text.replace(placeholder, f'<span class="math-inline">{formula}</span>')
        
        # 恢复代码块
        for i, code in enumerate(code_blocks):
            placeholder = f"<<<CODE{i}>>>"
            match = re.match(r'```(\w*)\n(.*?)```', code, re.DOTALL)
            if match:
                lang = match.group(1)
                code_content = self._escape_html(match.group(2))
                text = text.replace(placeholder, 
                    f'<pre><code class="language-{lang}">{code_content}</code></pre>')
        
        return text
    
    def _escape_html(self, text):
        """转义HTML特殊字符"""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))
    
    def _embed_image(self, alt, src):
        """嵌入图片为base64"""
        # 处理相对路径
        if not src.startswith(('http://', 'https://', 'data:')):
            # URL解码，处理%E6%B5%8B%E8%AF%95等编码的中文
            src_decoded = unquote(src)
            img_path = self.md_dir / src_decoded.lstrip('./')
            
            # 如果解码后的路径不存在，尝试原始路径
            if not img_path.exists():
                img_path = self.md_dir / src.lstrip('./')
            
            if img_path.exists():
                try:
                    with open(img_path, 'rb') as f:
                        img_data = f.read()
                    mime_type = mimetypes.guess_type(str(img_path))[0] or 'image/jpeg'
                    b64_data = base64.b64encode(img_data).decode('utf-8')
                    return f'<img src="data:{mime_type};base64,{b64_data}" alt="{alt}" />'
                except Exception as e:
                    return f'<span class="img-error">[图片加载失败: {alt} - {str(e)}]</span>'
            else:
                return f'<span class="img-error">[图片文件不存在: {src_decoded}]</span>'
        
        return f'<img src="{src}" alt="{alt}" />'
    
    def convert(self):
        """转换为HTML"""
        # 生成题目HTML，使用全局连续编号
        questions_html = ""
        for global_index, q in enumerate(self.questions, 1):
            questions_html += self._generate_question_html(q, global_index)
        
        # 使用模板
        html = HTML_TEMPLATE.format(
            title=self.title or "题库",
            description=self._process_markdown(self.description) if self.description else "",
            questions=questions_html,
            total_count=self.stats['total']
        )
        
        return html
    
    def _generate_question_html(self, q, global_num=None):
        """生成单个题目的HTML"""
        stem_html = self._process_markdown(q['stem'])
        qtype = q['type']
        is_multiple = '多选' in qtype
        is_judge = '判断' in qtype
        
        # 使用全局编号，如果没有则使用原始编号
        display_num = global_num if global_num else q['id']
        
        # 单选和判断题不需要提交按钮，点击直接显示
        need_submit = is_multiple
        
        html = f'''
<div class="question" data-qid="{q['id']}" data-type="{qtype}" data-answered="false" data-correct="false" data-auto-wrong="false" data-mark-important="false">
    <div class="mark-btns">
        <button class="mark-btn mark-important" onclick="toggleMark(this, 'important')" title="标记为重点">📌</button>
    </div>
    <div class="q-header">
        <span class="q-num">第 {display_num} 题</span>
        <span class="q-type">[{qtype}]</span>
        <span class="q-status"></span>
    </div>
    <div class="q-stem">{stem_html}</div>
    <div class="q-options">
'''
        
        # 生成选项
        for idx, opt in enumerate(q['options']):
            option_html = self._process_markdown(opt['text'])
            explanation_html = self._process_markdown(opt['explanation']) if opt['explanation'] else ""
            
            input_type = 'checkbox' if is_multiple else 'radio'
            correct_class = 'correct-option' if opt['is_correct'] else ''
            
            # 根据是否正确答案，添加不同的解析标签
            if explanation_html:
                if opt['is_correct']:
                    explanation_content = f'<div class="explanation correct-exp"><span class="exp-icon">✅ 正确</span> {explanation_html}</div>'
                else:
                    explanation_content = f'<div class="explanation wrong-exp"><span class="exp-icon">❌ 错误</span> {explanation_html}</div>'
            else:
                explanation_content = ''
            
            html += f'''
        <div class="option {correct_class}" data-correct="{str(opt['is_correct']).lower()}" onclick="{'' if is_multiple else 'selectSingleOption(this)'}">
            <label>
                <input type="{input_type}" name="q{q['id']}" value="{idx}" {'' if is_multiple else 'onclick="event.stopPropagation()"'}>
                <span class="option-label">{idx + 1}.</span>
                <span class="option-text">{option_html}</span>
            </label>
            {explanation_content}
        </div>
'''
        
        # 多选题需要提交按钮
        if need_submit:
            html += '''
    </div>
    <div class="q-actions">
        <button class="btn-check" onclick="checkAnswer(this)">查看答案</button>
        <button class="btn-reset" onclick="resetQuestion(this)" style="display:none;">重置</button>
    </div>
    <div class="q-result" style="display:none;"></div>
</div>
'''
        else:
            html += '''
    </div>
    <div class="q-actions" style="display:none;">
        <button class="btn-reset" onclick="resetQuestion(this)">重置</button>
    </div>
</div>
'''
        
        return html
    
    def get_stats(self):
        """获取统计信息"""
        return {
            'title': self.title,
            'total': self.stats['total'],
            'by_type': self.stats['by_type']
        }


# HTML模板
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
    <title>{title} - 手机刷题神器</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            line-height: 1.6;
            padding: 15px 10px;
            font-size: 16px;
        }}
        
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 6px 10px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 0.75rem;
            font-weight: 500;
            margin-bottom: 0;
            line-height: 1.2;
        }}
        
        .header .desc {{
            display: none;
        }}
        
        .header .stats {{
            display: none;
        }}
        
        .main {{
            padding: 10px;
            position: relative;
            min-height: calc(100vh - 150px);
        }}
        
        /* 卡片式题目容器 */
        #questions-container {{
            position: relative;
            min-height: 400px;
        }}
        
        /* 卡片模式：默认隐藏所有题目 */
        .question {{
            background: #ffffff;
            border-radius: 12px;
            padding: 20px 15px;
            margin-bottom: 60px;
            box-shadow: 0 2px 15px rgba(0, 0, 0, 0.08);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: none;
        }}
        
        /* 当前显示的卡片 */
        .question.active {{
            display: block;
        }}
        
        /* 滑入动画 */
        .question.slide-in-right {{
            animation: slideInRight 0.3s ease-out;
        }}
        
        .question.slide-in-left {{
            animation: slideInLeft 0.3s ease-out;
        }}
        
        @keyframes slideInRight {{
            from {{
                transform: translateX(100%);
                opacity: 0;
            }}
            to {{
                transform: translateX(0);
                opacity: 1;
            }}
        }}
        
        @keyframes slideInLeft {{
            from {{
                transform: translateX(-100%);
                opacity: 0;
            }}
            to {{
                transform: translateX(0);
                opacity: 1;
            }}
        }}
        
        .q-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 12px;
        }}
        
        .q-num {{
            font-weight: 700;
            color: #667eea;
            font-size: 1.1rem;
        }}
        
        .q-type {{
            background: #667eea;
            color: white;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
        }}
        
        .q-stem {{
            font-size: 1.05rem;
            color: #2c3e50;
            margin-bottom: 15px;
            line-height: 1.7;
        }}
        
        .q-options {{
            margin: 15px 0;
        }}
        
        .option {{
            background: white;
            border: 2px solid #e9ecef;
            border-radius: 10px;
            padding: 12px 15px;
            margin: 10px 0;
            cursor: pointer;
            transition: all 0.3s;
            position: relative;
        }}
        
        .option:hover {{
            border-color: #667eea;
            background: #f0f3ff;
        }}
        
        .option label {{
            display: flex;
            align-items: flex-start;
            gap: 10px;
            cursor: pointer;
            width: 100%;
        }}
        
        .option input {{
            margin-top: 4px;
            cursor: pointer;
            width: 18px;
            height: 18px;
            flex-shrink: 0;
        }}
        
        .option-label {{
            font-weight: 600;
            color: #667eea;
            min-width: 25px;
        }}
        
        .option-text {{
            flex: 1;
        }}
        
        .option.selected {{
            border-color: #667eea;
            background: #e3f2fd;
        }}
        
        .option.show-correct {{
            border-color: #28a745;
            background: #d4edda;
        }}
        
        .option.show-wrong {{
            border-color: #dc3545;
            background: #f8d7da;
        }}
        
        .explanation {{
            margin-top: 10px;
            padding: 10px;
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            border-radius: 6px;
            font-size: 0.95rem;
            color: #856404;
            display: none;
        }}
        
        .option.show-correct .explanation,
        .option.show-wrong .explanation {{
            display: block;
        }}
        
        .q-actions {{
            margin-top: 15px;
            display: flex;
            gap: 10px;
        }}
        
        .q-actions button {{
            flex: 1;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }}
        
        .btn-check {{
            background: #667eea;
            color: white;
        }}
        
        .btn-check:hover {{
            background: #5568d3;
        }}
        
        .btn-check:active {{
            transform: scale(0.98);
        }}
        
        .btn-reset {{
            background: #6c757d;
            color: white;
        }}
        
        .btn-reset:hover {{
            background: #5a6268;
        }}
        
        .q-result {{
            margin-top: 15px;
            padding: 12px;
            border-radius: 8px;
            font-weight: 600;
            text-align: center;
        }}
        
        .q-result.correct {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}
        
        .q-result.wrong {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}
        
        /* 工具栏样式 - 紧凑折叠版 */
        .toolbar {{
            background: white;
            padding: 8px 10px;
            margin: 0;
            border-bottom: 1px solid #e9ecef;
        }}
        
        .toolbar-row {{
            display: flex;
            gap: 6px;
            margin-bottom: 6px;
            flex-wrap: wrap;
        }}
        
        .toolbar-row:last-child {{
            margin-bottom: 0;
        }}
        
        .search-box {{
            flex: 1;
            min-width: 150px;
        }}
        
        .search-box input {{
            width: 100%;
            padding: 6px 10px;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            font-size: 0.85rem;
            transition: border-color 0.3s;
        }}
        
        .search-box input:focus {{
            outline: none;
            border-color: #667eea;
        }}
        
        .filter-group {{
            display: flex;
            gap: 5px;
            flex-wrap: wrap;
        }}
        
        .filter-btn {{
            padding: 5px 10px;
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.3s;
        }}
        
        .filter-btn:hover {{
            background: #e9ecef;
        }}
        
        .filter-btn.active {{
            background: #667eea;
            color: white;
            border-color: #667eea;
        }}
        
        .action-btns {{
            display: flex;
            gap: 5px;
        }}
        
        .action-btn {{
            padding: 5px 12px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.3s;
            white-space: nowrap;
        }}
        
        .action-btn:hover {{
            background: #5568d3;
        }}
        
        .action-btn:active {{
            transform: scale(0.98);
        }}
        
        /* 统计面板 - 极简版 */
        .stats-panel {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 4px 8px;
            margin: 0;
            display: flex;
            justify-content: space-around;
            text-align: center;
            font-size: 0.65rem;
        }}
        
        .stat-item {{
            flex: 1;
        }}
        
        .stat-value {{
            font-size: 0.85rem;
            font-weight: 700;
            margin-bottom: 0;
        }}
        
        .stat-label {{
            font-size: 0.6rem;
            opacity: 0.85;
        }}
        
        /* 题目状态标识 */
        .q-status {{
            margin-left: auto;
            padding: 3px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        
        .q-status.answered-correct {{
            background: #d4edda;
            color: #155724;
        }}
        
        .q-status.answered-wrong {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .q-status.marked-wrong {{
            background: #fff3cd;
            color: #856404;
        }}
        
        /* 错题标记按钮 */
        .mark-wrong-btn {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            opacity: 0.3;
            transition: all 0.3s;
        }}
        
        .mark-wrong-btn:hover {{
            opacity: 0.7;
            transform: scale(1.2);
        }}
        
        .mark-wrong-btn.marked {{
            opacity: 1;
        }}
        
        /* 标记按钮组 */
        .mark-btns {{
            position: absolute;
            top: 12px;
            right: 12px;
            display: flex;
            gap: 5px;
            z-index: 10;
        }}
        
        .mark-btn {{
            background: rgba(255, 255, 255, 0.9);
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 1.2rem;
            cursor: pointer;
            padding: 4px 8px;
            transition: all 0.2s;
            opacity: 0.4;
        }}
        
        .mark-btn:hover {{
            transform: scale(1.1);
            opacity: 0.8;
        }}
        
        .mark-btn.marked {{
            opacity: 1;
            border-color: #667eea;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
        }}
        
        /* 解析样式优化 */
        .explanation {{
            margin-top: 10px;
            padding: 12px;
            border-radius: 6px;
            font-size: 0.95rem;
            display: none;
            border-left: 4px solid;
        }}
        
        .correct-exp {{
            background: #d4edda;
            color: #155724;
            border-color: #28a745;
        }}
        
        .wrong-exp {{
            background: #f8d7da;
            color: #721c24;
            border-color: #dc3545;
        }}
        
        .exp-icon {{
            font-weight: 700;
            margin-right: 8px;
            font-size: 1.1rem;
        }}
        
        .option.show-correct {{
            border-color: #28a745;
            background: #d4edda !important;
        }}
        
        .option.show-wrong {{
            border-color: #dc3545;
            background: #f8d7da !important;
        }}
        
        /* 单选题/判断题：答题后显示所有解析 */
        .question[data-answered="true"] .option .explanation {{
            display: block;
        }}
        
        /* 多选题：只显示正确和错误选项的解析 */
        .option.show-correct .explanation,
        .option.show-wrong .explanation {{
            display: block;
        }}
        
        /* 隐藏题目的样式 */
        .question.hidden {{
            display: none;
        }}
        
        /* 沉浸式答题模式 */
        body.immersive-mode .header,
        body.immersive-mode .stats-panel,
        body.immersive-mode .toolbar {{
            display: none;
        }}
        
        body.immersive-mode .main {{
            padding: 15px 10px 70px 10px;
            min-height: calc(100vh - 70px);
        }}
        
        body.immersive-mode .question-counter {{
            top: 10px;
            right: 10px;
            font-size: 0.85rem;
            padding: 6px 12px;
        }}
        
        /* 切换模式按钮 */
        .mode-toggle {{
            position: fixed;
            top: 10px;
            left: 10px;
            background: rgba(102, 126, 234, 0.9);
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 12px;
            font-size: 0.75rem;
            cursor: pointer;
            z-index: 999;
            backdrop-filter: blur(10px);
        }}
        
        .mode-toggle:active {{
            transform: scale(0.95);
        }}
        
        body.immersive-mode .mode-toggle {{
            background: rgba(108, 117, 125, 0.9);
        }}
        
        /* 答题进度条 */
        .progress-bar-container {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: rgba(255, 255, 255, 0.3);
            z-index: 1001;
        }}
        
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, #28a745 0%, #20c997 100%);
            width: 0%;
            transition: width 0.3s ease;
        }}
        
        /* 夜间模式 */
        body.dark-mode {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        }}
        
        body.dark-mode .container {{
            background: #1e1e1e;
            color: #e0e0e0;
        }}
        
        body.dark-mode .header,
        body.dark-mode .stats-panel {{
            background: linear-gradient(135deg, #4a5568 0%, #2d3748 100%);
        }}
        
        body.dark-mode .toolbar {{
            background: #2d3748;
            border-color: #4a5568;
        }}
        
        body.dark-mode .question {{
            background: #2d3748;
            color: #e0e0e0;
        }}
        
        body.dark-mode .q-stem {{
            color: #e0e0e0;
        }}
        
        body.dark-mode .option {{
            background: #1a202c;
            border-color: #4a5568;
            color: #e0e0e0;
        }}
        
        body.dark-mode .option:hover {{
            background: #2d3748;
            border-color: #667eea;
        }}
        
        body.dark-mode .explanation {{
            background: #2d3748;
            border-left-color: #ffc107;
            color: #ffc107;
        }}
        
        body.dark-mode .search-box input {{
            background: #1a202c;
            border-color: #4a5568;
            color: #e0e0e0;
        }}
        
        body.dark-mode .filter-btn {{
            background: #1a202c;
            border-color: #4a5568;
            color: #e0e0e0;
        }}
        
        body.dark-mode .filter-btn.active {{
            background: #667eea;
            color: white;
        }}
        
        body.dark-mode .mobile-nav {{
            background: #2d3748;
            border-top-color: #4a5568;
        }}
        
        body.dark-mode .math-block {{
            background: #2a2a2a;
        }}
        
        /* 夜间模式切换按钮 */
        .dark-mode-toggle {{
            position: fixed;
            top: 10px;
            right: 50px;
            background: rgba(102, 126, 234, 0.9);
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 12px;
            font-size: 1.2rem;
            cursor: pointer;
            z-index: 999;
            backdrop-filter: blur(10px);
        }}
        
        .dark-mode-toggle:active {{
            transform: scale(0.95);
        }}
        
        /* 复习模式：展开所有题目和解析 */
        body.review-mode .question:not(.hidden) {{
            display: block !important;
            margin-bottom: 20px;
        }}
        
        body.review-mode .question.hidden {{
            display: none !important;
        }}
        
        body.review-mode .question .explanation {{
            display: block !important;
        }}
        
        body.review-mode .mobile-nav {{
            display: none;
        }}
        
        body.review-mode .main {{
            padding-bottom: 20px;
        }}
        
        /* 手机端：底部悬浮操作栏 */
        .mobile-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: white;
            box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.1);
            padding: 10px 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            z-index: 1000;
            border-top: 1px solid #e9ecef;
        }}
        
        .mobile-nav-btn {{
            flex: 1;
            padding: 12px 10px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            margin: 0 5px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 5px;
            min-height: 44px;
        }}
        
        .mobile-nav-btn:active {{
            transform: scale(0.95);
            background: #5568d3;
        }}
        
        .mobile-nav-btn.secondary {{
            background: #6c757d;
        }}
        
        .mobile-nav-btn.secondary:active {{
            background: #5a6268;
        }}
        
        .mobile-nav-btn.mark {{
            background: transparent;
            color: #ffc107;
            border: 2px solid #ffc107;
            font-size: 1.5rem;
            padding: 8px 15px;
        }}
        
        .mobile-nav-btn.mark.marked {{
            background: #ffc107;
            color: white;
        }}
        
        .question-counter {{
            position: fixed;
            top: 5px;
            right: 5px;
            background: rgba(102, 126, 234, 0.9);
            color: white;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            z-index: 999;
            backdrop-filter: blur(10px);
        }}
        
        /* 触摸反馈效果 */
        .option:active {{
            transform: scale(0.98);
        }}
        
        .btn-check:active,
        .btn-reset:active,
        .action-btn:active,
        .filter-btn:active {{
            transform: scale(0.95);
        }}
        
        /* 增大可点击区域 */
        .option {{
            min-height: 52px;
            padding: 15px;
        }}
        
        .mark-wrong-btn {{
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        /* 留出底部操作栏空间 */
        .main {{
            padding: 20px 15px 80px 15px;
        }}
        
        /* 数学公式样式 */
        .math-block {{
            margin: 15px 0;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 8px;
            overflow-x: auto;
        }}
        
        .math-inline {{
            display: inline-block;
            margin: 0 2px;
        }}
        
        /* 代码块样式 */
        pre {{
            margin: 10px 0;
            border-radius: 8px;
            overflow-x: auto;
        }}
        
        pre code {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 0.9rem;
            line-height: 1.5;
            display: block;
            padding: 15px;
        }}
        
        code {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        }}
        
        /* 行内代码样式 */
        :not(pre) > code {{
            background: #f0f0f0;
            color: #e83e8c;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
        }}
        
        /* 图片样式 */
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 10px 0;
            display: block;
        }}
        
        .img-error {{
            color: #dc3545;
            font-size: 0.9rem;
        }}
        
        /* 响应式 */
        @media (max-width: 768px) {{
            body {{
                padding: 10px 5px;
                font-size: 15px;
            }}
            
            .header h1 {{
                font-size: 1.3rem;
            }}
            
            .question {{
                padding: 15px;
            }}
            
            .q-stem {{
                font-size: 1rem;
            }}
        }}
        
        /* 暗色模式 */
        @media (prefers-color-scheme: dark) {{
            body {{
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            }}
            
            .container {{
                background: #1e1e1e;
                color: #e0e0e0;
            }}
            
            .question {{
                background: #2a2a2a;
            }}
            
            .q-stem {{
                color: #e0e0e0;
            }}
            
            .option {{
                background: #333;
                border-color: #444;
                color: #e0e0e0;
            }}
            
            .option:hover {{
                background: #3a3a5a;
                border-color: #667eea;
            }}
            
            .math-block {{
                background: #2a2a2a;
            }}
        }}
    </style>
    
    <!-- Highlight.js for 代码高亮 -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/styles/atom-one-dark.min.css">
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/highlight.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/python.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/javascript.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/java.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/cpp.min.js"></script>
    <script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11.9.0/build/languages/sql.min.js"></script>
    
    <!-- MathJax for 数学公式渲染 -->
    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [['$', '$']],
                displayMath: [['$$', '$$']]
            }},
            options: {{
                skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre']
            }}
        }};
    </script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
</head>
<body class="immersive-mode">
    <!-- 答题进度条 -->
    <div class="progress-bar-container">
        <div class="progress-bar" id="progress-bar"></div>
    </div>
    
    <!-- 模式切换按钮 -->
    <button class="mode-toggle" onclick="toggleMode()" id="mode-toggle-btn">📋 显示工具</button>
    
    <!-- 夜间模式切换 -->
    <button class="dark-mode-toggle" onclick="toggleDarkMode()" id="dark-mode-btn">🌙</button>
    
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            {description}
            <div class="stats">📊 共 {total_count} 道题</div>
        </div>
        
        <!-- 统计面板 -->
        <div class="stats-panel">
            <div class="stat-item">
                <div class="stat-value" id="total-count">{total_count}</div>
                <div class="stat-label">总题数</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="answered-count">0</div>
                <div class="stat-label">已答题</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="correct-count">0</div>
                <div class="stat-label">正确数</div>
            </div>
            <div class="stat-item">
                <div class="stat-value" id="accuracy-rate">0%</div>
                <div class="stat-label">正确率</div>
            </div>
        </div>
        
        <!-- 工具栏 -->
        <div class="toolbar">
            <div class="toolbar-row">
                <div class="search-box">
                    <input type="text" id="search-input" placeholder="🔍 搜索题目关键词..." oninput="filterQuestions()">
                </div>
            </div>
            <div class="toolbar-row">
                <div class="filter-group">
                    <button class="filter-btn active" data-filter="all" onclick="filterByType(this)">全部</button>
                    <button class="filter-btn" data-filter="单选题" onclick="filterByType(this)">单选题</button>
                    <button class="filter-btn" data-filter="多选题" onclick="filterByType(this)">多选题</button>
                    <button class="filter-btn" data-filter="判断题" onclick="filterByType(this)">判断题</button>
                    <button class="filter-btn" data-filter="auto-wrong" onclick="filterByType(this)">❌ 错题</button>
                    <button class="filter-btn" data-filter="important" onclick="filterByType(this)">📌 重点</button>
                </div>
                <div class="action-btns">
                    <button class="action-btn" onclick="shuffleQuestions()">🔀 随机</button>
                    <button class="action-btn" onclick="resetAll()">🔄 重置</button>
                    <button class="action-btn" onclick="toggleReviewMode()" id="review-mode-btn">📖 复习模式</button>
                </div>
            </div>
        </div>
        
        <div class="main" id="questions-container">
            {questions}
        </div>
        
        <!-- 手机端底部导航栏 -->
        <div class="mobile-nav">
            <button class="mobile-nav-btn secondary" onclick="prevQuestion()">← 上一题</button>
            <button class="mobile-nav-btn mark" id="mobile-mark-btn" onclick="toggleCurrentMark()">📌</button>
            <button class="mobile-nav-btn" onclick="nextQuestion()">下一题 →</button>
        </div>
        
        <!-- 题目计数器 -->
        <div class="question-counter" id="question-counter">1/{total_count}</div>
    </div>
    
    <script>
        // 初始化
        let currentQuestionIndex = 0;
        let touchStartX = 0;
        let touchStartY = 0;
        
        document.addEventListener('DOMContentLoaded', function() {{
            hljs.highlightAll();
            loadProgress();
            updateStats();
            initSwipeGesture();
            showQuestion(0); // 显示第一道题
            updateQuestionCounter();
            loadModePreference(); // 加载模式偏好
            loadDarkModePreference(); // 加载夜间模式偏好
        }});
        
        // 单选/判断题：点击选项直接显示答案
        function selectSingleOption(optionElement) {{
            const question = optionElement.closest('.question');
            const options = question.querySelectorAll('.option');
            const input = optionElement.querySelector('input');
            
            // 如果已经答过题，不允许再改
            if (question.dataset.answered === 'true') return;
            
            // 选中当前选项
            input.checked = true;
            
            // 获取正确答案
            const isCorrect = optionElement.dataset.correct === 'true';
            
            // 显示所有答案
            options.forEach(opt => {{
                const optCorrect = opt.dataset.correct === 'true';
                opt.classList.remove('show-correct', 'show-wrong');
                
                if (optCorrect) {{
                    opt.classList.add('show-correct');
                }} else if (opt.querySelector('input').checked) {{
                    opt.classList.add('show-wrong');
                }}
            }});
            
            // 标记题目已答
            question.dataset.answered = 'true';
            question.dataset.correct = isCorrect ? 'true' : 'false';
            
            // 自动标记错题
            if (!isCorrect) {{
                question.dataset.autoWrong = 'true';
            }}
            
            // 更新状态
            const statusSpan = question.querySelector('.q-status');
            statusSpan.textContent = isCorrect ? '✓ 正确' : '✗ 错误';
            statusSpan.className = 'q-status ' + (isCorrect ? 'answered-correct' : 'answered-wrong');
            
            // 显示重置按钮
            const resetBtn = question.querySelector('.btn-reset');
            if (resetBtn) resetBtn.style.display = 'inline-block';
            
            // 保存进度
            saveProgress();
            updateStats();
        }}
        
        // 多选题：提交答案
        function checkAnswer(btn) {{
            const question = btn.closest('.question');
            const options = question.querySelectorAll('.option');
            const inputs = question.querySelectorAll('input');
            
            // 获取用户选择
            const userAnswers = [];
            inputs.forEach((input, idx) => {{
                if (input.checked) {{
                    userAnswers.push(idx);
                }}
            }});
            
            if (userAnswers.length === 0) {{
                alert('请先选择答案！');
                return;
            }}
            
            // 获取正确答案
            const correctAnswers = [];
            options.forEach((opt, idx) => {{
                if (opt.dataset.correct === 'true') {{
                    correctAnswers.push(idx);
                }}
            }});
            
            // 判断正误
            const isCorrect = userAnswers.length === correctAnswers.length &&
                           userAnswers.every(ans => correctAnswers.includes(ans));
            
            // 显示结果
            options.forEach((opt, idx) => {{
                opt.classList.remove('show-correct', 'show-wrong');
                
                if (correctAnswers.includes(idx)) {{
                    opt.classList.add('show-correct');
                }} else if (userAnswers.includes(idx)) {{
                    opt.classList.add('show-wrong');
                }}
            }});
            
            // 标记题目已答
            question.dataset.answered = 'true';
            question.dataset.correct = isCorrect ? 'true' : 'false';
            
            // 自动标记错题
            if (!isCorrect) {{
                question.dataset.autoWrong = 'true';
            }}
            
            // 更新状态
            const statusSpan = question.querySelector('.q-status');
            statusSpan.textContent = isCorrect ? '✓ 正确' : '✗ 错误';
            statusSpan.className = 'q-status ' + (isCorrect ? 'answered-correct' : 'answered-wrong');
            
            // 切换按钮
            btn.style.display = 'none';
            question.querySelector('.btn-reset').style.display = 'inline-block';
            
            // 禁用选项
            inputs.forEach(input => input.disabled = true);
            
            // 自动标记错题
            if (!isCorrect) {{
                question.dataset.autoWrong = 'true';
            }}
            
            // 保存进度
            saveProgress();
            updateStats();
        }}
        
        // 重置题目
        function resetQuestion(btn) {{
            const question = btn.closest('.question');
            const options = question.querySelectorAll('.option');
            const inputs = question.querySelectorAll('input');
            
            // 清除选择
            inputs.forEach(input => {{
                input.checked = false;
                input.disabled = false;
            }});
            
            // 清除样式
            options.forEach(opt => {{
                opt.classList.remove('selected', 'show-correct', 'show-wrong');
            }});
            
            // 清除状态
            question.dataset.answered = 'false';
            question.dataset.correct = 'false';
            const statusSpan = question.querySelector('.q-status');
            statusSpan.textContent = '';
            statusSpan.className = 'q-status';
            
            // 切换按钮
            btn.style.display = 'none';
            const checkBtn = question.querySelector('.btn-check');
            if (checkBtn) checkBtn.style.display = 'inline-block';
            
            // 保存进度
            saveProgress();
            updateStats();
        }}
        
        // 标记错题
        function toggleWrongMark(btn) {{
            const question = btn.closest('.question');
            const isMarked = question.dataset.markedWrong === 'true';
            
            question.dataset.markedWrong = !isMarked ? 'true' : 'false';
            btn.textContent = !isMarked ? '⭐' : '☆';
            btn.classList.toggle('marked');
            
            saveProgress();
        }}
        
        // 标记功能（多标签）
        function toggleMark(btn, type) {{
            const question = btn.closest('.question');
            const dataKey = 'mark' + type.charAt(0).toUpperCase() + type.slice(1);
            const isMarked = question.dataset[dataKey] === 'true';
            
            question.dataset[dataKey] = !isMarked ? 'true' : 'false';
            btn.classList.toggle('marked');
            
            saveProgress();
        }}
        
        // 搜索过滤
        function filterQuestions() {{
            const keyword = document.getElementById('search-input').value.toLowerCase();
            const questions = document.querySelectorAll('.question');
            
            questions.forEach(q => {{
                const text = q.textContent.toLowerCase();
                q.classList.toggle('hidden', !text.includes(keyword));
            }});
            
            // 重新显示第一道题
            showQuestion(0, 'right');
        }}
        
        // 按题型过滤
        function filterByType(btn) {{
            const filter = btn.dataset.filter;
            const questions = document.querySelectorAll('.question');
            const body = document.body;
            
            // 更新按钮状态
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // 过滤题目
            questions.forEach(q => {{
                if (filter === 'all') {{
                    q.classList.remove('hidden');
                }} else if (filter === 'auto-wrong') {{
                    // 筛选自动错题：已答且错误的
                    const isAutoWrong = q.dataset.answered === 'true' && q.dataset.correct === 'false';
                    q.classList.toggle('hidden', !isAutoWrong);
                }} else if (filter === 'important') {{
                    q.classList.toggle('hidden', q.dataset.markImportant !== 'true');
                }} else {{
                    q.classList.toggle('hidden', !q.dataset.type.includes(filter));
                }}
            }});
            
            // 错题和重点筛选时，自动进入列表模式（类似复习模式）
            if (filter === 'auto-wrong' || filter === 'important') {{
                body.classList.add('review-mode');
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }} else {{
                // 其他筛选保持卡片模式
                body.classList.remove('review-mode');
                // 重新显示第一道题
                showQuestion(0, 'right');
            }}
        }}
        
        // 随机打乱题目
        function shuffleQuestions() {{
            const container = document.getElementById('questions-container');
            const questions = Array.from(container.querySelectorAll('.question'));
            
            // Fisher-Yates 洗牌算法
            for (let i = questions.length - 1; i > 0; i--) {{
                const j = Math.floor(Math.random() * (i + 1));
                [questions[i], questions[j]] = [questions[j], questions[i]];
            }}
            
            // 重新添加到容器
            questions.forEach(q => container.appendChild(q));
            
            // 显示第一道题
            showQuestion(0, 'right');
        }}
        
        // 重置所有
        function resetAll() {{
            if (!confirm('确定要重置所有答题记录吗？')) return;
            
            const questions = document.querySelectorAll('.question');
            questions.forEach(q => {{
                const resetBtn = q.querySelector('.btn-reset');
                if (resetBtn && resetBtn.style.display !== 'none') {{
                    resetQuestion(resetBtn);
                }}
                q.dataset.markedWrong = 'false';
                const markBtn = q.querySelector('.mark-wrong-btn');
                if (markBtn) {{
                    markBtn.textContent = '☆';
                    markBtn.classList.remove('marked');
                }}
            }});
            
            localStorage.removeItem('qbank_progress');
            updateStats();
        }}
        
        // 更新统计
        function updateStats() {{
            const questions = document.querySelectorAll('.question');
            let total = questions.length;
            let answered = 0;
            let correct = 0;
            
            questions.forEach(q => {{
                if (q.dataset.answered === 'true') {{
                    answered++;
                    if (q.dataset.correct === 'true') {{
                        correct++;
                    }}
                }}
            }});
            
            const accuracy = answered > 0 ? Math.round(correct / answered * 100) : 0;
            
            document.getElementById('total-count').textContent = total;
            document.getElementById('answered-count').textContent = answered;
            document.getElementById('correct-count').textContent = correct;
            document.getElementById('accuracy-rate').textContent = accuracy + '%';
            
            // 更新进度条
            updateProgressBar();
        }}
        
        // 保存进度到localStorage
        function saveProgress() {{
            const questions = document.querySelectorAll('.question');
            const progress = {{}};
            
            questions.forEach(q => {{
                const qid = q.dataset.qid;
                progress[qid] = {{
                    answered: q.dataset.answered,
                    correct: q.dataset.correct,
                    markImportant: q.dataset.markImportant || 'false'
                }};
            }});
            
            localStorage.setItem('qbank_progress', JSON.stringify(progress));
        }}
        
        // 加载进度
        function loadProgress() {{
            const saved = localStorage.getItem('qbank_progress');
            if (!saved) return;
            
            const progress = JSON.parse(saved);
            const questions = document.querySelectorAll('.question');
            
            questions.forEach(q => {{
                const qid = q.dataset.qid;
                if (progress[qid]) {{
                    q.dataset.answered = progress[qid].answered;
                    q.dataset.correct = progress[qid].correct;
                    q.dataset.markImportant = progress[qid].markImportant || 'false';
                    
                    // 恢复状态显示
                    if (q.dataset.answered === 'true') {{
                        const statusSpan = q.querySelector('.q-status');
                        const isCorrect = q.dataset.correct === 'true';
                        statusSpan.textContent = isCorrect ? '✓ 正确' : '✗ 错误';
                        statusSpan.className = 'q-status ' + (isCorrect ? 'answered-correct' : 'answered-wrong');
                    }}
                    
                    // 恢复重点标记
                    if (q.dataset.markImportant === 'true') {{
                        const btn = q.querySelector('.mark-important');
                        if (btn) btn.classList.add('marked');
                    }}
                }}
            }});
        }}
        
        // ========== 手机端专属功能 ==========
        
        // 获取可见题目列表
        function getVisibleQuestions() {{
            return Array.from(document.querySelectorAll('.question:not(.hidden)'));
        }}
        
        // 显示指定题目（卡片模式）
        function showQuestion(index, direction = 'right') {{
            const questions = getVisibleQuestions();
            if (index < 0 || index >= questions.length) return;
            
            // 隐藏所有题目
            questions.forEach(q => {{
                q.classList.remove('active', 'slide-in-right', 'slide-in-left');
            }});
            
            // 显示当前题目
            const currentQ = questions[index];
            currentQ.classList.add('active');
            
            // 添加滑入动画
            if (direction === 'right') {{
                currentQ.classList.add('slide-in-right');
            }} else {{
                currentQ.classList.add('slide-in-left');
            }}
            
            currentQuestionIndex = index;
            updateQuestionCounter();
        }}
        
        // 更新题目计数器
        function updateQuestionCounter() {{
            const questions = getVisibleQuestions();
            const current = currentQuestionIndex + 1;
            const total = questions.length;
            document.getElementById('question-counter').textContent = `${{current}}/${{total}}`;
            
            // 更新底部标记按钮状态
            const currentQ = questions[currentQuestionIndex];
            const markBtn = document.getElementById('mobile-mark-btn');
            if (currentQ && markBtn) {{
                if (currentQ.dataset.markImportant === 'true') {{
                    markBtn.style.background = 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)';
                }} else {{
                    markBtn.style.background = '';
                }}
            }}
        }}
        
        // 上一题
        function prevQuestion() {{
            const questions = getVisibleQuestions();
            if (currentQuestionIndex > 0) {{
                showQuestion(currentQuestionIndex - 1, 'left');
            }}
        }}
        
        // 下一题
        function nextQuestion() {{
            const questions = getVisibleQuestions();
            if (currentQuestionIndex < questions.length - 1) {{
                showQuestion(currentQuestionIndex + 1, 'right');
            }}
        }}
        
        // 切换当前题目的重点标记
        function toggleCurrentMark() {{
            const questions = getVisibleQuestions();
            const currentQ = questions[currentQuestionIndex];
            if (currentQ) {{
                const markBtn = currentQ.querySelector('.mark-important');
                if (markBtn) {{
                    toggleMark(markBtn, 'important');
                    // 更新底部按钮状态
                    const mobileBtn = document.getElementById('mobile-mark-btn');
                    if (currentQ.dataset.markImportant === 'true') {{
                        mobileBtn.style.background = 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)';
                    }} else {{
                        mobileBtn.style.background = '';
                    }}
                }}
            }}
        }}
        
        // 初始化滑动手势
        function initSwipeGesture() {{
            const container = document.getElementById('questions-container');
            
            container.addEventListener('touchstart', function(e) {{
                touchStartX = e.touches[0].clientX;
                touchStartY = e.touches[0].clientY;
            }}, {{ passive: true }});
            
            container.addEventListener('touchend', function(e) {{
                const touchEndX = e.changedTouches[0].clientX;
                const touchEndY = e.changedTouches[0].clientY;
                
                const deltaX = touchEndX - touchStartX;
                const deltaY = touchEndY - touchStartY;
                
                // 只有横向滑动大于竖向滑动时才触发
                if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {{
                    if (deltaX > 0) {{
                        // 右滑 - 上一题
                        prevQuestion();
                    }} else {{
                        // 左滑 - 下一题
                        nextQuestion();
                    }}
                }}
            }}, {{ passive: true }});
        }}
        
        // 切换沉浸式模式
        function toggleMode() {{
            const body = document.body;
            const btn = document.getElementById('mode-toggle-btn');
            
            if (body.classList.contains('immersive-mode')) {{
                // 切换到完整模式
                body.classList.remove('immersive-mode');
                btn.innerHTML = '🎯 专注答题';
            }} else {{
                // 切换到沉浸模式
                body.classList.add('immersive-mode');
                btn.innerHTML = '📋 显示工具';
            }}
            
            // 保存模式选择
            localStorage.setItem('immersive-mode', body.classList.contains('immersive-mode'));
        }}
        
        // 加载模式选择
        function loadModePreference() {{
            const isImmersive = localStorage.getItem('immersive-mode');
            if (isImmersive === 'false') {{
                toggleMode();
            }}
        }}
        
        // 更新进度条
        function updateProgressBar() {{
            const questions = document.querySelectorAll('.question');
            const total = questions.length;
            let answered = 0;
            
            questions.forEach(q => {{
                if (q.dataset.answered === 'true') answered++;
            }});
            
            const progress = total > 0 ? (answered / total * 100) : 0;
            document.getElementById('progress-bar').style.width = progress + '%';
        }}
        
        // 切换夜间模式
        function toggleDarkMode() {{
            const body = document.body;
            const btn = document.getElementById('dark-mode-btn');
            
            if (body.classList.contains('dark-mode')) {{
                body.classList.remove('dark-mode');
                btn.innerHTML = '🌙';
            }} else {{
                body.classList.add('dark-mode');
                btn.innerHTML = '☀️';
            }}
            
            localStorage.setItem('dark-mode', body.classList.contains('dark-mode'));
        }}
        
        // 加载夜间模式偏好
        function loadDarkModePreference() {{
            const isDark = localStorage.getItem('dark-mode');
            if (isDark === 'true') {{
                document.body.classList.add('dark-mode');
                document.getElementById('dark-mode-btn').innerHTML = '☀️';
            }}
        }}
        
        // 切换复习模式
        function toggleReviewMode() {{
            const body = document.body;
            const btn = document.getElementById('review-mode-btn');
            
            if (body.classList.contains('review-mode')) {{
                // 退出复习模式，回到卡片模式
                body.classList.remove('review-mode');
                btn.innerHTML = '📖 复习模式';
                btn.style.background = '';
                
                // 恢复卡片模式
                showQuestion(currentQuestionIndex, 'right');
            }} else {{
                // 进入复习模式
                body.classList.add('review-mode');
                btn.innerHTML = '📝 答题模式';
                btn.style.background = 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)';
                
                // 滚动到顶部
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
            
            localStorage.setItem('review-mode', body.classList.contains('review-mode'));
        }}
    </script>
</body>
</html>
"""
