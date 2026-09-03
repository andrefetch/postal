def get_skills_section() -> str:
    """Gets the skills section, Generate SKILL.md spec section"""

    return """ # SKILL.md Specification
    
    - Repos often contain SKILL.md files.

    - These files define reusable procedures, workflows, or specilized capabilites for working on specialized kinds of tasks.

    - The scope of a SKILL.md file is the directory tree rooted at the folder which contains it.

    - A SKILL.md file may contain instructions such as:
        - How to perform a type of task.
        - Recommend tools or commands to be used.
        - Required workflows or types of validation steps.
        - Domain-specific Debugging conventions.
        - Procedures for debugging, testing, deploying or reviewing code.
        - Design instructions for both code quality and web/app design.

    - Skills are invoked when the current task matches the purpose described by the SKILL.md file.

    - A nested SKILL.md takes precdence over a parent SKILL.md when instructions are conflicting.

    - Direct system, developer, user or config instrctions' take precedence over SKILL.md instructions.

    - Skills should be treated as reusable procedures rather than general repository instructions.

    - When a task requires a skill, the agent should read the applicable SKILL.md before performing that task.

    """