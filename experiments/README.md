$ git submodule add https://github.com/solvin-ai/demo demo

$ wget https://github.com/github/codeql-cli-binaries/releases/download/v2.21.3/codeql-linux64.zip
$ unzip codeql-linux64.zip
$ rm codeql-linux64.zip
$ cd codeql
$ ./codeql database create yaniv-db --language=python --source-root=../demo/
$ ./codeql pack download codeql/python-queries
$ ./codeql database analyze yaniv-db codeql/python-queries:codeql-suites/python-security-extended.qls --format=sarif-latest --output=results.sarif

$ semgrep scan --json --quiet | jq | pbcopy

$ snyk auth
$ snyk test

$ brew install grype
$ grype dir:./demo/
