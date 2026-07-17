'use client'

import { useEffect, useState } from 'react'

const copy = {
  zh: {
    title: 'QA 目录', all: '全部 QA', create: '新建 QA 目录', adjust: '调整顺序', finish: '完成调整',
    empty: '暂无 QA 目录', createChild: '新建子目录', rename: '重命名', delete: '删除',
    name: '目录名称', namePlaceholder: '请输入目录名称', parent: '上级目录', root: '无（一级目录）',
    cancel: '取消', save: '保存', nameRequired: '请输入目录名称', nameTooLong: '目录名称最多输入 50 个字符',
    duplicate: '同一上级目录下已存在同名目录', depth: 'QA 目录最多支持 3 级',
    nonEmpty: '该目录下仍有内容，请先移动或删除后再操作', created: 'QA 目录已新建',
    updated: 'QA 目录已更新', deleted: 'QA 目录已删除', sortFailed: 'QA 目录顺序保存失败',
    deleteTitle: '删除 QA 目录', deleteBody: '确定删除以下 QA 目录？删除后不可恢复。',
    directoryName: '目录名称', directoryPath: '目录路径', deleteConfirm: '确定删除',
    noDirectoryHint: '请先新建 QA 目录', currentEmpty: '该目录暂无 QA', createHere: '在此目录新建 QA',
    directoryColumn: '所属目录', directorySelect: '所属目录', directoryPlaceholder: '请选择 QA 目录',
    directoryRequired: '请选择 QA 目录', directoryOnlyUpdated: 'QA 所属目录已更新',
  },
  en: {
    title: 'QA directories', all: 'All QA', create: 'Create QA directory', adjust: 'Reorder', finish: 'Finish',
    empty: 'No QA directories', createChild: 'Create subdirectory', rename: 'Rename', delete: 'Delete',
    name: 'Directory name', namePlaceholder: 'Enter a directory name', parent: 'Parent directory', root: 'None (top level)',
    cancel: 'Cancel', save: 'Save', nameRequired: 'Enter a directory name', nameTooLong: 'Directory name must be 50 characters or fewer',
    duplicate: 'A directory with this name already exists under the same parent', depth: 'QA directories support up to 3 levels',
    nonEmpty: 'This directory still contains content. Move or delete it first.', created: 'QA directory created',
    updated: 'QA directory updated', deleted: 'QA directory deleted', sortFailed: 'Failed to save QA directory order',
    deleteTitle: 'Delete QA directory', deleteBody: 'Are you sure you want to delete this QA directory? This action cannot be undone.',
    directoryName: 'Directory name', directoryPath: 'Directory path', deleteConfirm: 'Delete',
    noDirectoryHint: 'Create a QA directory first', currentEmpty: 'No QA in this directory', createHere: 'Create QA here',
    directoryColumn: 'Directory', directorySelect: 'Directory', directoryPlaceholder: 'Select a QA directory',
    directoryRequired: 'Select a QA directory', directoryOnlyUpdated: 'QA directory updated',
  },
} as const

export type QaDirectoryCopy = (typeof copy)['zh'] | (typeof copy)['en']

export function useQaDirectoryCopy(): QaDirectoryCopy {
  const [language, setLanguage] = useState<'zh' | 'en'>('zh')
  useEffect(() => {
    const locale = document.documentElement.lang || navigator.language
    setLanguage(locale.toLowerCase().startsWith('en') ? 'en' : 'zh')
  }, [])
  return copy[language]
}
