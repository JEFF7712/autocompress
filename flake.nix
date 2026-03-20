{
  description = "autocompress — Hutter Prize autoresearch dev environment";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in {
      devShells = forAll (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.gcc        # C++ compiler
            pkgs.xz.dev     # lzma.h + liblzma
            pkgs.pkg-config # so train.py can find liblzma flags
            pkgs.uv         # Python package manager
          ];
        };
      });
    };
}
