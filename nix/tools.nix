# The runtime of ./rc ingest and ./rc research: document converters and Python libraries, pinned by the
# nixpkgs of flake.lock. ./rc builds it with `nix build -f nix/tools.nix`, which reads only this file and
# flake.lock, so an instance full of committed sources is never copied into the store on every command.
{
  pkgs ?
    let
      lock = builtins.fromJSON (builtins.readFile ../flake.lock);
      locked = lock.nodes.${lock.nodes.root.inputs.nixpkgs}.locked;
    in
    import (builtins.fetchTree locked) { },
}:
let
  python = pkgs.python3.withPackages (ps: [
    ps.python-pptx
    ps.openpyxl
  ]);
in
pkgs.buildEnv {
  name = "rc-tools";
  paths = [
    python
    pkgs.pandoc
    pkgs.poppler-utils
    pkgs.git
    pkgs.gh
  ];
}
