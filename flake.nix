{
  description = "Research Center: ingest what you know, grill a topic, research it with critiqued, cited evidence";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
  };

  outputs =
    { self, nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
      mkSystem =
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          tools = import ./nix/tools.nix { inherit pkgs; };
          python = "${tools}/bin/python3";
          validator = pkgs.writeShellApplication {
            name = "rc-validate";
            runtimeInputs = [ tools ];
            text = ''
              python3 ${self}/scripts/validate-knowledge.py "$PWD"
              exec python3 ${self}/scripts/validate-research-center.py "$PWD"
            '';
          };
          check =
            name: script:
            pkgs.runCommand "research-center-${name}" { nativeBuildInputs = [ tools ]; } ''
              export HOME=$TMPDIR
              ${script}
              touch "$out"
            '';
        in
        {
          packages = {
            inherit tools;
            default = tools;
          };

          checks = {
            knowledge = check "knowledge" "${python} ${self}/scripts/validate-knowledge.py ${self}";
            research-center = check "contract" "${python} ${self}/scripts/validate-research-center.py ${self}";
            agent-configs = check "agent-configs" ''
              ${python} ${self}/scripts/agent-configs.py ${self} check
              ${python} -B ${self}/scripts/agent_configs_test.py
            '';
            rule-hooks = check "rule-hooks" "${python} -B ${self}/scripts/rule_hooks_test.py";
            providers = check "providers" "cd ${self}/scripts/runner && ${python} -B providers_test.py";
            ingest = check "ingest" ''
              ${python} -B ${self}/scripts/ingest/secrets_test.py
              ${python} -B ${self}/scripts/ingest/ingest_test.py
            '';
            research = check "research" "${python} -B ${self}/scripts/research/research_test.py";
          };

          apps = {
            default = {
              type = "app";
              program = "${validator}/bin/rc-validate";
            };
            validate = {
              type = "app";
              program = "${validator}/bin/rc-validate";
            };
          };

          devShell = pkgs.mkShell {
            packages = [
              tools
              pkgs.nixfmt
            ];
          };

          formatter = pkgs.nixfmt;
        };
      perSystem = forAllSystems mkSystem;
    in
    {
      packages = nixpkgs.lib.mapAttrs (_: value: value.packages) perSystem;
      checks = nixpkgs.lib.mapAttrs (_: value: value.checks) perSystem;
      apps = nixpkgs.lib.mapAttrs (_: value: value.apps) perSystem;
      devShells = nixpkgs.lib.mapAttrs (_: value: { default = value.devShell; }) perSystem;
      formatter = nixpkgs.lib.mapAttrs (_: value: value.formatter) perSystem;
    };
}
