{
  description = "autocompress: Hutter Prize world-record harness";

  # Pinned: nixos-unstable dropped llvmPackages_17 (2025-08); fx2-cmix's PGO
  # build is clang-17-validated, so the pin is load-bearing. The container
  # image is built from this same pin so laptop and homelab toolchains are
  # byte-identical (binary_bytes is part of the score).
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
  # 24.05's uv (0.1.x) predates uv.lock support; take uv (and other fast-moving
  # tools) from unstable while the compiler stays on the 24.05 pin.
  inputs.nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-unstable,
    }:
    let
      systems = [ "x86_64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f s nixpkgs.legacyPackages.${s});
      unstable = s: nixpkgs-unstable.legacyPackages.${s};
      toolchain =
        pkgs:
        let
          clang17 = pkgs.llvmPackages_17.clang;
        in
        [
          # LLVM 17's -march=native falls back to generic x86-64 (no AVX2) on
          # CPUs missing from its lookup table (e.g. 13th-gen Intel mobile),
          # silently disabling vectorized model code. AUTOCOMPRESS_MARCH
          # rewrites native to an explicit target; leave it unset on CPUs LLVM
          # detects correctly (e.g. the homelab's Zen 1 workers).
          (pkgs.writeShellScriptBin "clang++-17" ''
            args=()
            for a in "$@"; do
              case "$a" in
                -march=native) args+=(-march=''${AUTOCOMPRESS_MARCH:-native}) ;;
                -mtune=native) args+=(-mtune=''${AUTOCOMPRESS_MARCH:-native}) ;;
                *) args+=("$a") ;;
              esac
            done
            exec ${clang17}/bin/clang++ "''${args[@]}"
          '')
          (pkgs.writeShellScriptBin "llvm-profdata-17" ''exec ${pkgs.llvmPackages_17.llvm}/bin/llvm-profdata "$@"'')
          (pkgs.writeShellScriptBin "upx-ucl" ''exec ${pkgs.upx}/bin/upx "$@"'')
          clang17
          pkgs.llvmPackages_17.llvm
          pkgs.upx
          pkgs.gnumake
        ];
    in
    {
      devShells = forAll (
        s: pkgs: {
          # AUTOCOMPRESS_MARCH is intentionally not set here: benchmark.py
          # exports it from config.toml's march_override, keeping all
          # machine-specific state in that one untracked file.
          default = pkgs.mkShell { packages = toolchain pkgs ++ [ (unstable s).uv ]; };
        }
      );

      packages = forAll (
        s: pkgs: {
          runner-image = pkgs.dockerTools.buildLayeredImage {
            name = "autocompress-runner";
            tag = "0.1.0";
            contents = toolchain pkgs ++ [
              (unstable s).uv
              pkgs.bashInteractive
              pkgs.coreutils
              pkgs.gnugrep
              pkgs.gnused
              pkgs.gawk
              pkgs.findutils
              pkgs.git
              pkgs.util-linux
              pkgs.cacert
              pkgs.dockerTools.usrBinEnv
            ];
            extraCommands = ''
              mkdir -p -m 1777 tmp
              mkdir -p work etc/autocompress
            '';
            config = {
              User = "1000:1000";
              WorkingDir = "/work";
              Env = [
                "SSL_CERT_FILE=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
                "HOME=/work"
              ];
              Cmd = [
                "/bin/bash"
                "/etc/autocompress/entrypoint.sh"
              ];
            };
          };
        }
      );
    };
}
