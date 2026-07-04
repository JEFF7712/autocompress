{
  description = "autocompress: Hutter Prize world-record harness";

  # Pinned: nixos-unstable dropped llvmPackages_17 (2025-08); fx2-cmix's PGO
  # build is clang-17-validated, so the pin is load-bearing.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";

  outputs =
    { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      devShells = forAll (
        pkgs:
        let
          clang17 = pkgs.llvmPackages_17.clang;
          wrappers = [
            (pkgs.writeShellScriptBin "clang++-17" ''exec ${clang17}/bin/clang++ "$@"'')
            (pkgs.writeShellScriptBin "llvm-profdata-17" ''exec ${pkgs.llvmPackages_17.llvm}/bin/llvm-profdata "$@"'')
            (pkgs.writeShellScriptBin "upx-ucl" ''exec ${pkgs.upx}/bin/upx "$@"'')
          ];
        in
        {
          default = pkgs.mkShell {
            packages = wrappers ++ [
              clang17
              pkgs.llvmPackages_17.llvm
              pkgs.upx
              pkgs.gnumake
              pkgs.uv
            ];
          };
        }
      );
    };
}
