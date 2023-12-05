#compdef twist twistd trial conch cftp ckeygen pyhtmlizer tkconch
#
# This is the ZSH completion file for Twisted commands. It calls the current
# command-line with the special "--_shell-completion" option which is handled
# by twisted.python.usage. t.p.usage then generates zsh code on stdout to
# handle the completions for this particular command-line.
#
# 3rd parties that wish to provide zsh completion for commands that
# use t.p.usage may copy this file and change the first line to reference
# the name(s) of their command(s).
#
# This file is included in the official Zsh distribution as
# Completion/Unix/Command/_twisted

# redirect stderr to /dev/null otherwise deprecation warnings may get puked all
# over the user's terminal if completing options for a deprecated command.
# Redirect stderr to a file to debug errors.
local cmd output
cmd=("$words[@]" --_shell-completion zsh:$CURRENT)
output=$("$cmd[@]" 2>/dev/null)

if [[ $output == "#compdef "* ]]; then
    # Looks like we got a valid completion function - so eval it to produce
    # the completion matches.
    eval $output
else
    echo "\nCompletion error running command:" ${(qqq)cmd}
    echo -n "If output below is unhelpful you may need to edit this file and "
    echo    "redirect stderr to a file."
    echo "Expected completion function, but instead got:"
    echo $output
    return 1
fi
