# 前端孤立节点详细分析

总计: 759 个节点 来自 131 个文件

## frontend/src/i18n/locales/en.json (178 nodes)

- common.loading
- common.save
- common.cancel
- common.close
- common.refresh
- common.retry
- common.copy
- common.copied
- common.search
- common.noResults
- common.project
- nav.dashboard
- nav.project
- nav.notes
- nav.search
- nav.chat
- nav.molecules
- nav.sar
- nav.workflow
- nav.fileTree
- nav.switchProject
- nav.confirmSwitchProject
- nav.settings
- welcome.title
- welcome.subtitle
- welcome.createProject
- welcome.openProject
- welcome.recentProjects
- welcome.emptyRecent
- welcome.projectName
- ... and 148 more

## frontend/src/i18n/locales/zh-CN.json (178 nodes)

- common.loading
- common.save
- common.cancel
- common.close
- common.refresh
- common.retry
- common.copy
- common.copied
- common.search
- common.noResults
- common.project
- nav.dashboard
- nav.project
- nav.notes
- nav.search
- nav.chat
- nav.molecules
- nav.sar
- nav.workflow
- nav.fileTree
- nav.switchProject
- nav.confirmSwitchProject
- nav.settings
- welcome.title
- welcome.subtitle
- welcome.createProject
- welcome.openProject
- welcome.recentProjects
- welcome.emptyRecent
- welcome.projectName
- ... and 148 more

## frontend/src/hooks/useAnimations.ts (15 nodes)

- scaleIn
- scaleInBounce
- slideFromLeft
- slideFromBottom
- staggerContainer
- staggerContainerSlow
- staggerContainerFast
- staggerItem
- staggerItemFadeOnly
- hoverScale
- hoverLift
- hoverBorderHighlight
- fadeUpWithDelay()
- fadeInWithDelay()
- makeStaggerContainer()

## frontend/src/types/index.ts (12 nodes)

- Message
- Project
- SearchResult
- ModelStatus
- HealthResponse
- FileNode
- ChatMessage
- CompoundEntry
- ActivityEntry
- FindingEntry
- UncertainItem
- DocumentMetadata

## frontend/src/App.tsx (11 nodes)

- ProjectView
- Search
- Chat
- MoleculeLibrary
- Workflow
- SARAnalysis
- Dashboard
- Notes
- RouteFallback()
- App()
- AppRoutes()

## frontend/src/components/SettingsModal.tsx (11 nodes)

- SettingsState
- DEFAULT_SETTINGS
- GeneralSection()
- AISection()
- EmbeddingSection()
- RerankerSection()
- AppearanceSection()
- ServerSection()
- AboutSection()
- SECTION_ICONS
- Props

## frontend/src/styles/patterns.ts (10 nodes)

- SIZES
- surfaceBlock
- surfaceBlockNoPadding
- surfaceBlockAccent
- chip
- centerContainer
- vstack()
- fullscreenBackdrop
- modalPanel
- PATTERNS

## frontend/src/api/tauri/agent.ts (9 nodes)

- AgentStreamEvent
- DocumentReport
- CompoundEntry
- ActivityEntry
- FindingEntry
- UncertainItem
- DocumentMetadata
- StructuredData
- PostProcessResult

## frontend/src/components/dashboard/Sparkline.tsx (8 nodes)

- SparklineProps
- Sparkline()
- BarChartProps
- BarChart()
- DonutChartProps
- DonutChart()
- HeatmapProps
- Heatmap()

## frontend/src/components/ui/Toast.tsx (8 nodes)

- globalToasts
- listeners
- ToastContextValue
- ToastContext
- toastColor()
- ToastIcon()
- ToastContainerProps
- positionStyle

## frontend/src/components/molecule/CorrectionPanel.tsx (7 nodes)

- CorrectionItem
- CorrectionPanelProps
- StatusBadge()
- SmilesDiff()
- ValidationResultProps
- ValidationResult()
- CorrectionPanel()

## frontend/src/components/settings/ModelComponents.tsx (7 nodes)

- ModelSelectorProps
- DownloadState
- DownloadProgressBarProps
- DownloadModel
- ModelCardProps
- DownloadedModel
- DownloadedModelItemProps

## frontend/src/api/tauri/pdf.ts (6 nodes)

- PdfClassification
- PdfExtraction
- Heading
- SectionChunk
- DocProgressEvent
- OcrLayoutResult

## frontend/src/components/ErrorBoundary.tsx (6 nodes)

- Props
- State
- .constructor()
- .getDerivedStateFromError()
- .componentDidCatch()
- .render()

## frontend/src/components/PdfCanvas.tsx (6 nodes)

- isTextItem()
- docCache
- getCachedDoc()
- PageInfo
- Props
- PdfCanvas()

## frontend/src/components/SARAnalysis.tsx (6 nodes)

- moleculesToSession()
- SessionOverview()
- StatBox()
- OverviewTab()
- CorrectionTab()
- RGroupTab()

## frontend/src/components/ui/Progress.tsx (6 nodes)

- ProgressStatus
- ProgressType
- ProgressProps
- colorMap
- Progress()
- StepsProps

## frontend/src/api/client.ts (5 nodes)

- SARCompoundInput
- RGroupMatrixResponse
- ActivityHeatmapCell
- ActivityHeatmapResponse
- ValidateResponse

## frontend/src/components/Chat.tsx (5 nodes)

- MermaidCode
- renderInlineLatex()
- isSmiles()
- smilesToImgUrl()
- LocalMessage

## frontend/src/components/Notes.tsx (5 nodes)

- BacklinksPanelProps
- BacklinksPanel()
- TagPillProps
- TagPill()
- NoteListItemProps

## frontend/src/components/Welcome.tsx (5 nodes)

- RecentProject
- sanitizePath()
- Props
- Page
- Welcome()

## frontend/src/components/sar/rgroup/HeatmapPanel.tsx (5 nodes)

- HeatmapPanel()
- HeatmapRow()
- HeatmapCellRowProps
- ColorLegendProps
- ColorLegend()

## frontend/src/components/settings/ModelsTab.tsx (5 nodes)

- DownloadState
- ProgressBar()
- ModelCard()
- DownloadedModelItem()
- ModelsTab()

## frontend/src/components/ui/DataTable.tsx (5 nodes)

- DataTableColumn
- DataTableProps
- sizeMap
- SortState
- DataTable()

## frontend/src/styles/responsive.ts (5 nodes)

- BREAKPOINTS
- Breakpoint
- media
- responsive()
- useContainerWidth()

## frontend/src/api/tauri/kb.ts (4 nodes)

- KbSearchResult
- KbSearchChunk
- TreeNode
- PageContent

## frontend/src/api/tauri/project.ts (4 nodes)

- ProjectInfo
- ProjectResponse
- DocumentEntry
- FileNode

## frontend/src/api/tauri/text.ts (4 nodes)

- TextChunkResult
- PageClassification
- extractSmilesCandidates()
- extractActivities()

## frontend/src/components/LatexText.tsx (4 nodes)

- Props
- LatexText()
- TextPart
- parseLatex()

## frontend/src/components/OcrOverlay.tsx (4 nodes)

- pdfToCss()
- blockTypeColor()
- blockTypeLabel()
- OcrOverlay()

## frontend/src/components/Sidebar.tsx (4 nodes)

- Props
- NAV_ITEMS
- NavButton()
- Sidebar()

## frontend/src/components/molecule/MoleculeDetailPanel.tsx (4 nodes)

- MermaidCode
- ChemDescriptors
- MoleculeDetailPanel()
- DescItem()

## frontend/src/components/molecule/MoleculeDisplay.tsx (4 nodes)

- MermaidCode
- MoleculeDisplayProps
- ATOMIC_WEIGHTS
- ConfidenceBadge()

## frontend/src/components/ui/AvatarGroup.tsx (4 nodes)

- AvatarItem
- AvatarGroupProps
- statusColors
- AvatarGroup()

## frontend/src/components/ui/Breadcrumb.tsx (4 nodes)

- BreadcrumbItem
- BreadcrumbProps
- sizeMap
- Breadcrumb()

## frontend/src/components/ui/Pagination.tsx (4 nodes)

- PaginationProps
- sizeMap
- getPageNumbers()
- Pagination()

## frontend/src/components/ui/StatusBadge.tsx (4 nodes)

- StatusType
- StatusBadgeProps
- config
- StatusBadge()

## frontend/src/components/ui/Tabs.tsx (4 nodes)

- TabsProps
- sizeMap
- Tabs()
- TabPanelProps

## frontend/src/components/workflow/LibrarySection.tsx (4 nodes)

- LIBRARY_INFO
- LibRow()
- LibrarySectionProps
- LibrarySection()

## frontend/src/components/workflow/StatCard.tsx (4 nodes)

- StatCardProps
- BG_COLORS
- TEXT_COLORS
- StatCard()

## frontend/src/utils/errors.ts (4 nodes)

- .constructor()
- .toJSON()
- ERROR_MESSAGES
- toAppError()

## frontend/src/api/tauri/__tests__/audit.test.ts (3 nodes)

- mockInvoke
- InvokeCall
- lastCallArgs()

## frontend/src/components/ConfirmationPanel.tsx (3 nodes)

- PageClassification
- ConfirmationPanelProps
- ConfirmationPanel()

## frontend/src/components/Dashboard.tsx (3 nodes)

- StatCardProps
- StatCard()
- DashboardStats

## frontend/src/components/FileTree.tsx (3 nodes)

- FileNode
- Props
- TreeNode()

## frontend/src/components/MoleculeOverlay.tsx (3 nodes)

- pdfToCss()
- confColor()
- MoleculeOverlay()

## frontend/src/components/MoleculeReviewPanel.tsx (3 nodes)

- Molecule
- MoleculeReviewPanelProps
- MoleculeReviewPanel()

## frontend/src/components/OcrResultPanel.tsx (3 nodes)

- blockTypeColor()
- blockTypeLabel()
- OcrResultPanel()

## frontend/src/components/Search.tsx (3 nodes)

- ResultItem
- HINTS
- mapResult()

## frontend/src/components/molecule/MoleculeEditorDialog.tsx (3 nodes)

- structServiceProvider
- MoleculeEditorDialogProps
- MoleculeEditorDialog()

## frontend/src/components/notes/editor/EditorToolbar.tsx (3 nodes)

- TrashIconSvg()
- EditorToolbarProps
- EditorToolbar()

## frontend/src/components/ui/AlertBanner.tsx (3 nodes)

- AlertBannerProps
- toneMap
- AlertBanner()

## frontend/src/components/ui/Badge.tsx (3 nodes)

- BadgeProps
- variantMap
- Badge()

## frontend/src/components/ui/BodyText.tsx (3 nodes)

- BodyTextProps
- sizeMap
- BodyText()

## frontend/src/components/ui/Button.tsx (3 nodes)

- variantStyles
- sizeStyles
- Button()

## frontend/src/components/ui/EnvCard.tsx (3 nodes)

- EnvCardProps
- variantStyles
- EnvCard()

## frontend/src/components/ui/MermaidCode.tsx (3 nodes)

- initMermaid()
- MermaidCodeProps
- MermaidCode()

## frontend/src/components/ui/Tooltip.tsx (3 nodes)

- TooltipProps
- positionStyles
- Tooltip()

## frontend/src/components/ui/TreeNode.tsx (3 nodes)

- FileNode
- TreeNodeProps
- TreeNode()

## frontend/src/hooks/useProjectRoot.ts (3 nodes)

- getProjectRoot()
- setProjectRoot()
- useProjectRoot()

## frontend/src/i18n/index.ts (3 nodes)

- resources
- Language
- detectLanguage()

## frontend/src/api/__tests__/download.test.ts (2 nodes)

- mockFetchJson
- mockSseStream

## frontend/src/api/settings.ts (2 nodes)

- AppSettings
- SettingsResponse

## frontend/src/api/tauri/__tests__/agent.test.ts (2 nodes)

- mockInvoke
- mockListen

## frontend/src/api/tauri/__tests__/kb.test.ts (2 nodes)

- mockInvoke
- mockListen

## frontend/src/api/tauri/molecule.ts (2 nodes)

- MoleculeRecord_
- MoleculeStats

## frontend/src/api/tauri/notes.ts (2 nodes)

- NoteLink
- Note

## frontend/src/components/ChatContextChip.tsx (2 nodes)

- ChatContextChipProps
- ChatContextChip()

## frontend/src/components/MarkdownViewer.tsx (2 nodes)

- Props
- MarkdownViewer()

## frontend/src/components/PDFViewer.tsx (2 nodes)

- PDFViewerProps
- PDFViewer()

## frontend/src/components/animations/AnimatedPage.tsx (2 nodes)

- Props
- AnimatedPage()

## frontend/src/components/animations/FadeIn.tsx (2 nodes)

- Props
- FadeIn()

## frontend/src/components/animations/ScaleButton.tsx (2 nodes)

- Props
- ScaleButton()

## frontend/src/components/animations/StaggerContainer.tsx (2 nodes)

- Props
- item

## frontend/src/components/notes/editor/MarkdownWithWikiLinks.tsx (2 nodes)

- MarkdownWithWikiLinksProps
- MarkdownWithWikiLinks()

## frontend/src/components/notes/editor/ToolbarButton.tsx (2 nodes)

- ToolbarButtonProps
- ToolbarButton()

## frontend/src/components/project/PdfViewer.tsx (2 nodes)

- MermaidCode
- PdfViewer()

## frontend/src/components/project/ProjectDashboard.tsx (2 nodes)

- IndexProgress
- ProjectDashboard()

## frontend/src/components/sar/rgroup/CoreScaffoldCard.tsx (2 nodes)

- CoreScaffoldCardProps
- CoreScaffoldCard()

## frontend/src/components/settings/EnvironmentSection.tsx (2 nodes)

- ResourceItem
- EnvironmentSection()

## frontend/src/components/ui/Avatar.tsx (2 nodes)

- AvatarProps
- Avatar()

## frontend/src/components/ui/Caption.tsx (2 nodes)

- CaptionProps
- Caption()

## frontend/src/components/ui/CollapsibleSection.tsx (2 nodes)

- CollapsibleSectionProps
- CollapsibleSection()

## frontend/src/components/ui/EmptyState.tsx (2 nodes)

- EmptyStateProps
- EmptyState()

## frontend/src/components/ui/HoverCard.tsx (2 nodes)

- HoverCardProps
- HoverCard()

## frontend/src/components/ui/IconButton.tsx (2 nodes)

- IconButtonProps
- IconButton()

## frontend/src/components/ui/IconContainer.tsx (2 nodes)

- IconContainerProps
- IconContainer()

## frontend/src/components/ui/LibStatusRow.tsx (2 nodes)

- LibStatusRowProps
- LibStatusRow()

## frontend/src/components/ui/PageTitle.tsx (2 nodes)

- PageTitleProps
- PageTitle()

## frontend/src/components/ui/ProgressBar.tsx (2 nodes)

- ProgressBarProps
- ProgressBar()

## frontend/src/components/ui/SectionHeader.tsx (2 nodes)

- SectionHeaderProps
- SectionHeader()

## frontend/src/components/ui/SectionTitle.tsx (2 nodes)

- SectionTitleProps
- SectionTitle()

## frontend/src/components/ui/Skeleton.tsx (2 nodes)

- SkeletonProps
- Skeleton()

## frontend/src/components/ui/Spinner.tsx (2 nodes)

- SpinnerProps
- Spinner()

## frontend/src/components/ui/StatCard.tsx (2 nodes)

- StatCardProps
- StatCard()

## frontend/src/components/ui/Toolbar.tsx (2 nodes)

- ToolbarProps
- Toolbar()

## frontend/src/components/workflow/ModelCard.tsx (2 nodes)

- TYPE_COLORS
- ModelCard()

## frontend/src/components/workflow/PathCard.tsx (2 nodes)

- PathCardProps
- PathCard()

## frontend/src/components/workflow/sections.tsx (2 nodes)

- PathSectionProps
- ModelsSectionProps

## frontend/src/context/AppContext.tsx (2 nodes)

- AppState
- AppContext

## frontend/src/hooks/useRenderTiming.ts (2 nodes)

- useRenderTiming.ts
- useRenderTiming()

## frontend/src/hooks/useSidecarEvents.ts (2 nodes)

- SidecarLogEvent
- SidecarStatusEvent

## frontend/src/api/moldet.ts (1 nodes)

- DetectPageResponse

## frontend/src/api/tauri-events.ts (1 nodes)

- TauriEventName

## frontend/src/api/tauri/__tests__/chem.test.ts (1 nodes)

- mockInvoke

## frontend/src/api/tauri/__tests__/environment.test.ts (1 nodes)

- mockInvoke

## frontend/src/api/tauri/environment.ts (1 nodes)

- ResourceStatusItem

## frontend/src/api/tauri/gesim.ts (1 nodes)

- GesimMappingResult

## frontend/src/components/Header.tsx (1 nodes)

- Header()

## frontend/src/components/Workflow.tsx (1 nodes)

- Environment()

## frontend/src/components/notes/NoteEditor.tsx (1 nodes)

- NoteEditor()

## frontend/src/components/notes/editor/EditView.tsx (1 nodes)

- EditView()

## frontend/src/components/sar/RGroupMatrix.tsx (1 nodes)

- RGroupMatrixView()

## frontend/src/components/sar/rgroup/MatrixTable.tsx (1 nodes)

- MatrixTable()

## frontend/src/components/ui/AddMoleculeDialog.tsx (1 nodes)

- AddMoleculeDialogProps

## frontend/src/components/ui/Card.tsx (1 nodes)

- Card()

## frontend/src/components/ui/FolderPicker.tsx (1 nodes)

- FolderPickerProps

## frontend/src/components/ui/Input.tsx (1 nodes)

- Input()

## frontend/src/components/ui/PageContainer.tsx (1 nodes)

- PageContainerProps

## frontend/src/components/ui/ResponsiveContainer.tsx (1 nodes)

- Direction

## frontend/src/components/ui/SettingSection.tsx (1 nodes)

- SettingSection()

## frontend/src/components/ui/TextArea.tsx (1 nodes)

- TextArea()

## frontend/src/components/ui/__tests__/Button.test.tsx (1 nodes)

- Button.test.tsx

## frontend/src/components/ui/__tests__/Card.test.tsx (1 nodes)

- Card.test.tsx

## frontend/src/components/ui/__tests__/Tabs.test.tsx (1 nodes)

- defaultItems

## frontend/src/components/workflow/types.ts (1 nodes)

- ModelLocation

## frontend/src/context/index.ts (1 nodes)

- index.ts

## frontend/src/hooks/__tests__/useDocResult.test.ts (1 nodes)

- mockListen

## frontend/src/hooks/useTheme.ts (1 nodes)

- Theme

## frontend/src/test/setup.ts (1 nodes)

- setup.ts

## frontend/src/utils/roiText.ts (1 nodes)

- TextItem
