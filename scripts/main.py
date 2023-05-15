# https://github.com/stone-zeng/tl-depend-analysis/

import dataclasses
import json
import os
import subprocess
import sys
from argparse import ArgumentParser
from typing import Any

from file_parser import Parser


TLPDB_PATH            = 'data/texlive.tlpdb'
TL_DEPEND_PATH        = 'data/tl-depend.json'
L3BUILD_UNPACKED_PATH = "../build/unpacked"
TEST_PATH             = "../test"

# INIT_PACKAGES = set(['latexmk', 'biblatex', 'cleveref', 'enumitem', 'footmisc', 'ntheorem',
#                      'unicode-math', 'tex-gyre', 'tex-gyre-math', 'xits', 'lexend', 'cm-unicode',
#                      'biblatex-gb7714-2015', 'biber', 'bibtex', 'makeindex'])

arg_parser = ArgumentParser(description='Optional packages')
arg_parser.add_argument('--pkg', type=str, default='')

INIT_PACKAGES = set(arg_parser.parse_args().pkg.split())

TEXMFDIST_PATH = subprocess.run(
    ['kpsewhich', '-var-value', 'TEXMFDIST'],
    capture_output=True, check=True).stdout.decode().strip()
# TEXMFDIST_PATH = '/usr/local/texlive/2023/texmf-dist'


@dataclasses.dataclass
class Package:
    name: str
    category: str
    revision: int
    tl_depend: list[str]
    depend: list[str]
    runfiles: list[str]


class PackageEncoder(json.JSONEncoder):

    def default(self, o):
        if isinstance(o, Package):
            return {
                'name': o.name,
                'depend': o.depend,
                'tl_depend': o.tl_depend,
            }
            # return dataclasses.asdict(o)
        return json.JSONEncoder.default(self, o)


class TLDepend:

    def __init__(self):
        self.packages: list[Package] = []
        self.file_mappings: dict[str, str] = {}
        self.njuthesis_depend: set[str] = []

    def parse_tlpdb(self):
        with open(TLPDB_PATH, 'r', encoding='utf-8') as fp:
            items = fp.read().strip().split('\n\n')
        for item in items:
            lines = item.split('\n')
            _, name = lines[0].split()
            if not name.startswith('00') and '.' not in name:
                self.packages.append(
                    Package(name=name, depend=[], **self._parse_tlpdb_item(lines)))

    @staticmethod
    def _parse_tlpdb_item(lines: list[str]):
        package: dict[str, Any] = {
            'tl_depend': [],
            'runfiles': [],
        }
        runfiles_flag = False
        for line in lines:
            key, *value = line.strip().split(maxsplit=1)
            value = value[0] if value else None
            match key:
                case 'category':
                    package['category'] = value
                case 'revision':
                    package['revision'] = int(value) if value else -1
                case 'depend':
                    package['tl_depend'].append(value)
                case 'runfiles':
                    runfiles_flag = True
                case _ if runfiles_flag:
                    if line.startswith(' '):
                        package['runfiles'].append(line.strip())
                    else:
                        runfiles_flag = False
        return package

    def get_file_mappings(self, verbose: bool = False):
        for package in self.packages:
            if package.name.endswith('-dev'):
                if verbose:
                    print('Skip dev package:', package.name, file=sys.stderr)
                continue
            for file in package.runfiles:
                if file.startswith('RELOC') or file.startswith('texmf-dist'):
                    _, path = file.split('/', maxsplit=1)
                    # if path.startswith('fonts'):
                    #     continue
                    if (name := os.path.basename(path)) in self.file_mappings:
                        if verbose:
                            print('Duplicate file:', file, file=sys.stderr)
                    else:
                        self.file_mappings[name] = package.name

    def get_njuthesis_depend(self, file_paths: list):
        depend: set[str] = INIT_PACKAGES
        for fp in file_paths:
            for f in os.listdir(fp):
                print(fp, f)
                full_path = os.path.join(fp, f)
                if not os.path.isdir(full_path):
                    depend.update(self._get_depend_from_file(full_path))
        depend.discard("njuthesis")
        self.njuthesis_depend = depend

    def update_njuthesis_depend(self):
        init_depend = self.njuthesis_depend.copy()
        full_depend: set[str] = set()
        with open(TL_DEPEND_PATH, mode="r", encoding='utf-8') as f:
            data = json.load(f)
        while len(init_depend) > 0:
            # recursive method
            pkg = init_depend.pop()
            full_depend.update([pkg])
            for entry in data:
                if entry["name"] == pkg:
                    temp = set(entry["depend"])
                    common = full_depend.intersection(temp)
                    init_depend.update(temp.difference(common))
            print(pkg, len(init_depend),len(full_depend))
        self.njuthesis_depend = sorted(full_depend)

    def _get_depend_from_file(self, file: str):
        depend: set[str] = set()
        parser = Parser(file)
        parser.parse()
        for d in parser.depend:
            try:
                depend.add(self.file_mappings[d])
            except KeyError:
                print('Dependency not found:', d, file=sys.stderr)
        return depend


def main():
    analyzer = TLDepend()
    analyzer.parse_tlpdb()
    analyzer.get_file_mappings()
    analyzer.get_njuthesis_depend([L3BUILD_UNPACKED_PATH, TEST_PATH])
    analyzer.update_njuthesis_depend()
    print(analyzer.njuthesis_depend)
    os.system('tlmgr install ' + ' '.join(analyzer.njuthesis_depend))


if __name__ == '__main__':
    main()
