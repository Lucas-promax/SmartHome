import MarkdownIt from 'markdown-it'

// 模型输出只解析 Markdown，不允许原始 HTML 或自动加载远程图片。
const markdown = new MarkdownIt({ html: false, breaks: true, linkify: true }).disable('image')
const renderLink = markdown.renderer.rules.link_open || ((tokens, index, options, env, self) => self.renderToken(tokens, index, options))
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index].attrSet('target', '_blank')
  tokens[index].attrSet('rel', 'noopener noreferrer')
  return renderLink(tokens, index, options, env, self)
}

export function renderMarkdown(content) {
  return markdown.render(content || '')
}
