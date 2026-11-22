const skillAliases: Record<string, [string, string]> = {
 'brainstorming': ['Plan a Feature', 'Clarify the goal, compare approaches, and settle the design before building.'],
 'systematic-debugging': ['Find the Root Cause', 'Reproduce a bug, trace the failure, and verify the fix.'],
 'writing-plans': ['Write an Implementation Plan', 'Turn an agreed design into steps, with files to change and checks to run.'],
 'executing-plans': ['Implement a Plan', 'Work through an existing implementation plan and verify each checkpoint.'],
 'test-driven-development': ['Write a Test Before the Fix', 'Capture the failure in a test before implementing the change.'],
 'verification-before-completion': ['Verify Before Delivery', 'Run fresh checks before reporting that the work is complete.'],
 'requesting-code-review': ['Prepare Changes for Code Review', 'Check a change and prepare the context a reviewer needs.'],
 'receiving-code-review': ['Work Through Review Feedback', 'Evaluate review comments and verify the changes they require.'],
 'using-git-worktrees': ['Create an Isolated Git Workspace', 'Work on a separate branch in its own directory.'],
 'finishing-a-development-branch': ['Finish a Git Branch', 'Review the merge, pull request, and cleanup options for finished work.'],
 'dispatching-parallel-agents': ['Delegate Independent Tasks', 'Identify independent pieces of work and coordinate their results.'],
 'subagent-driven-development': ['Implement with Agent Review', 'Implement separate tasks and review each result.'],
 'using-superpowers': ['Choose a Development Workflow', 'Identify the workflow that fits the current engineering task.'],
 'writing-skills': ['Write and Test a Skill', 'Create reusable instructions and check that they guide the intended task.'],
 'grill-me': ['Clarify Requirements by Interview', 'Ask focused questions to uncover missing decisions and assumptions.'],
 'to-prd': ['Write Product Requirements', 'Turn project discussions into a product requirements document.'],
 'to-issues': ['Break Work into Issues', 'Turn a plan into independently actionable work items.'],
 'tdd': ['Develop with Tests First', 'Build the implementation in small steps guided by tests.'],
 'frontend-design': ['Design a Web Interface', 'Create a usable, visually coherent frontend.'],
 'webapp-testing': ['Test a Web App in the Browser', 'Exercise workflows and inspect browser behavior.'],
 'docx': ['Work with Word Documents', 'Create, edit, and review Word documents.'],
 'xlsx': ['Work with Spreadsheets', 'Build and check spreadsheets, formulas, and data tables.'],
 'pptx': ['Build a Slide Deck', 'Create and revise presentations.'],
 'pdf': ['Work with PDFs', 'Create, read, and inspect PDFs.'],
 'skill-creator': ['Create a Reusable Skill', 'Write and evaluate reusable task instructions.'],
};

const collectionAliases: Record<string, string> = {
 'obra/superpowers': 'Software Development Workflows',
 'mattpocock/skills': 'Product and Engineering Workflows',
 'anthropics/skills': 'Documents, Design and Development',
 'openai/skills': 'OpenAI Skill Catalog',
 'vercel-labs/agent-skills': 'React and Web Development',
 'nextlevelbuilder/ui-ux-pro-max-skill': 'UI and UX Design',
};

export function skillTitle(name: string) {
 return skillAliases[name]?.[0] ?? name.replace(/[-_]+/g,' ').replace(/\b[a-z]/g, letter=>letter.toUpperCase());
}

export function skillPurpose(name: string, description: string) {
 return skillAliases[name]?.[1] ?? description;
}

export function collectionTitle(repository: string) {
 const [owner,name] = repository.split('/');
 return collectionAliases[repository.toLowerCase()] ?? (name ? name === 'skills' ? skillTitle(owner) + ' Skills' : skillTitle(name) : repository);
}

export function matchesSkill(skill: {name:string;description:string;repository?:string}, query: string) {
 const fields = [skillTitle(skill.name),skill.name,skillPurpose(skill.name,skill.description),skill.description,
  skill.repository,skill.repository && collectionTitle(skill.repository)];
 return fields.join(' ').toLowerCase().includes(query.trim().toLowerCase());
}
