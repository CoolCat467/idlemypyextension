# IdleMypyExtension
Python IDLE extension to preform mypy analysis on an open file

## What does this extension do?
This IDLE extension hooks into the mypy daemon to type check the currently
open file or provide a function signature suggestion for the nearest function
to the top from the current input cursor location. When type checking the
currently open file with the "Type Check File" command, it will add comments
to your code wherever mypy had something to say about about that line.
You can remove type comments from the currently selected text with the
"Remove Type Comments" command.
Additionally, you can jump to the next comment this extension created in
your file with the "Find Next Type Comment" command. Finally, you can add
an inferred function signature to your file with the "Suggest Signature"
command when you are close by a function definition.

Note: On use, creates folder `mypy` within the idle user directory.
On linux systems, this is usually `~/.idlerc/mypy`.

## Installation
1) Go to terminal and install with `pip install idlemypyextension`.
2) Run command `idlemypyextension`. You will likely see a message saying
`idlemypyextension not in system registered extensions!`. Run the command
given to add idlemypyextension to your system's IDLE extension config file.
3) Again run command `idlemypyextension`. This time, you should see the
following output: `Config should be good!`.
4) Open IDLE, go to `Options` -> `Configure IDLE` -> `Extensions`.
If everything went well, alongside `ZzDummy` there should be and
option called `idlemypyextension`. This is where you can configure how
idlemypyextension works.


## Information on options
`action_max_sec` controls how long an action is allowed to take at most,
in seconds.
Values under 5 will make no effect

For `daemon_flags`, see `mypy --help` for a list of valid flags.
This extension sets the following flags to be able to work properly:
```
    --hide-error-context
    --no-color-output
    --show-absolute-path
    --no-error-summary
    --cache-dir="~/.idlerc/mypy"
```

If you add the `--show-column-numbers` flag to `daemon_flags`, when using the
"Type Check File" command, it will add a helpful little `^` sign
in a new line below the location of the mypy message that provided a column
number, as long as that comment wouldn't break your file's indentation too much.

If you add the `--show-error-codes` flag to `daemon_flags`, when using the
"Type Check File" command, when it puts mypy's comments in your code, it will
tell you what type of error that comment is. For example, it would change the
error comment
```python
# types: error: Incompatible types in assignment (expression has type "str", variable has type "int")
```
to
```python
# types: assignment error: Incompatible types in assignment (expression has type "str", variable has type "int")
```

`search_wrap` toggles weather searching for next type comment will wrap
around or not.

`suggest_replace` toggles weather Suggest Signature will replace the
existing function definition or just add a comment with the suggested
definition

`timeout_mins` controls how long the mypy daemon will time out after,
in minutes.
