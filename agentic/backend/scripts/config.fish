set -x HOSTNAME (hostname)
set -x HISTTIMEFORMAT "%d/%m/%y %T "

set -g -x fish_greeting ''
set -g theme_nerd_fonts yes

export OPENAI_API_KEY='sk-proj-'
export GITHUB_TOKEN='ghp_'

set -gx API_TOKEN_OPENAI $OPENAI_API_KEY
set -gx API_TOKEN_GITHUB $GITHUB_TOKEN

# set -gx PATH $HOME/miniconda3/bin $PATH  # commented out by conda initialize

#set -xg __fish_trace_debug 1

##################################################################################################################

set -gx PATH /home/yaniv/.local/bin /home/linuxbrew/.linuxbrew/bin $PATH

starship init fish | source

##################################################################################################################

alias l='ls -lhA --group-directories-first --time-style=+"%Y-%m-%d %r" --color=always'
alias h='cd ~/dev/solvin/agentic/backend'
alias tree='tree -C --prune'
alias grep='grep --color=always -aT'
alias less='less -R'
alias watch='watch -cd'
alias diff='diff --color'
alias cp='cp -a'
alias scr='xrandr --output "DP-1-2" --auto --output "eDP-1" --off'
alias upd='sudo apt -y update ; sudo apt -y upgrade -o APT::Get::Always-Include-Phased-Updates=true ; sudo apt -y upgrade --with-new-pkgs ; sudo sudo apt -y full-upgrade ; sudo apt -y dist-upgrade --fix-broken ; sudo apt -y install unattended-upgrades ; sudo do-release-upgrade ; sudo apt -y autoremove ; sudo apt -y autoclean ; sudo apt install -f ; apt list --upgradable -a ; sudo apt install fwupd ; sudo fwupdmgr refresh ; sudo fwupdmgr get-updates ; sudo fwupdmgr update ; sudo snap refresh ; brew update ; brew upgrade ; echo && uname -a && echo && lsb_release -a'
alias pbcopy='xclip -selection clipboard'
alias pbpaste='xclip -selection clipboard -o'


alias gdiff='git diff --minimal -w'
alias cursor='~/Applications/cursor.AppImage --no-sandbox'

#alias dk="docker run -v /var/run/docker.sock:/var/run/docker.sock --rm laniksj/dfimage"
#alias c='git add -A && git commit -m "updates [ci skip]" && git push && git status'
#alias scr='xrandr --output "DP-1-2" --auto --output "eDP-1" --off'
#alias h='cd $NANO_HOME/build/docker'
#alias h1='cd $NANO_HOME/controlplane'
#alias h2='cd $NANO_HOME/.nano_storage'

##################################################################################################################


if not functions -q fisher
    set -q XDG_CONFIG_HOME; or set XDG_CONFIG_HOME ~/.config
    curl https://git.io/fisher --create-dirs -sLo $XDG_CONFIG_HOME/fish/functions/fisher.fish
    fish -c fisher
end

#fisher add jorgebucaran/fish-nvm
#fisher add danhper/fish-ssh-agent
#fisher add edc/bass

##################################################################################################################

# Enable the below lines to get Nano to work:
 #ssh-add
 #
 #set -Ux NANO_HOME $HOME/s/nanolabs-io
 #set -Ux BUILD_HOME $NANO_HOME/build/docker 
 #bass source $BUILD_HOME/dev-env.sh

##################################################################################################################

#set -Ux GOPATH $HOME/go
set -Ux GO111MODULE on

#set PATH $PATH /home/yaniv/.pulumi/bin
#set PATH $PATH /home/yaniv/nano/emsdk /home/yaniv/nano/emsdk/upstream/emscripten /home/yaniv/nano/emsdk/node/12.9.1_64bit/bin
#set -Ux fish_user_paths

#export EMSDK=/home/yaniv/nano/emsdk
#export EM_CONFIG=/home/yaniv/.emscripten
#export EMSDK_NODE=/home/yaniv/nano/emsdk/node/12.9.1_64bit/bin/node

##################################################################################################################

#kubectl completion fish | source

##################################################################################################################

# >>> conda initialize >>>
# !! Contents within this block are managed by 'conda init' !!
#if test -f /home/yaniv/miniconda3/bin/conda
#    eval /home/yaniv/miniconda3/bin/conda "shell.fish" "hook" $argv | source
#else
#    if test -f "/home/yaniv/miniconda3/etc/fish/conf.d/conda.fish"
#        . "/home/yaniv/miniconda3/etc/fish/conf.d/conda.fish"
#    else
#        set -x PATH "/home/yaniv/miniconda3/bin" $PATH
#    end
#end
# <<< conda initialize <<<

# Function to auto‐activate a Python virtual environment if found.
function auto_activate_venv --description "Auto-activate local Python virtualenv if present"
    # Check for an "env" folder with activate.fish.
    if test -f env/bin/activate.fish
        # If no virtual environment is active, simply activate it.
        if not set -q VIRTUAL_ENV
            echo "Activating virtual environment from ./env"
            source env/bin/activate.fish
        else
            # Only compare paths if VIRTUAL_ENV is set.
            set current_env (realpath "$VIRTUAL_ENV")
            set local_env (realpath env)
            if test "$current_env" != "$local_env"
                if functions -q deactivate
                    echo "Deactivating current virtual environment..."
                    deactivate 2>/dev/null
                end
                echo "Activating virtual environment from ./env"
                source env/bin/activate.fish
            end
        end
    # If no "env", check for a "venv" folder.
    else if test -f venv/bin/activate.fish
        if not set -q VIRTUAL_ENV
            echo "Activating virtual environment from ./venv"
            source venv/bin/activate.fish
        else
            set current_env (realpath "$VIRTUAL_ENV")
            set local_env (realpath venv)
            if test "$current_env" != "$local_env"
                if functions -q deactivate
                    echo "Deactivating current virtual environment..."
                    deactivate 2>/dev/null
                end
                echo "Activating virtual environment from ./venv"
                source venv/bin/activate.fish
            end
        end
    else
        # Optionally, deactivate any active virtual environment if none is found locally.
        if set -q VIRTUAL_ENV
            if functions -q deactivate
                echo "Deactivating virtual environment (none found in this directory)..."
                deactivate 2>/dev/null
            end
        end
    end
end

# Call the function at shell startup.
auto_activate_venv

# Run auto_activate_venv every time the current directory (PWD) changes.
function onpwd_change --on-variable PWD
    auto_activate_venv
end

####################

source /home/linuxbrew/.linuxbrew/share/fish/vendor_completions.d/asdf.fish

eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
