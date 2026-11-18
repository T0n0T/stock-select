use std::{env, fs, path::PathBuf};

fn main() {
    let Some(out_dir) = env::var_os("OUT_DIR") else {
        return;
    };
    let Some(profile_dir) = PathBuf::from(out_dir).ancestors().nth(3).map(PathBuf::from) else {
        return;
    };
    let library_name = if cfg!(target_os = "windows") {
        "duckdb.dll"
    } else if cfg!(target_os = "macos") {
        "libduckdb.dylib"
    } else {
        "libduckdb.so"
    };
    let source = env::var_os("DEP_DUCKDB_LIB_DIR")
        .or_else(|| env::var_os("DEP_DUCKDB_INCLUDE"))
        .map(PathBuf::from)
        .map(|dir| dir.join(library_name))
        .filter(|path| path.is_file())
        .or_else(|| {
            let download_root = profile_dir.parent()?.join("duckdb-download");
            fs::read_dir(download_root)
                .ok()?
                .flat_map(|entry| entry.ok())
                .map(|entry| entry.path())
                .flat_map(|path| fs::read_dir(path).into_iter().flatten().flatten())
                .map(|entry| entry.path().join(library_name))
                .find(|candidate| candidate.is_file())
        });
    if let Some(source) = source {
        if let Err(error) = fs::copy(source, profile_dir.join(library_name)) {
            println!("cargo:warning=unable to stage {library_name}: {error}");
        }
    }

    if cfg!(target_os = "linux") {
        println!("cargo:rustc-link-arg=-Wl,-rpath,$ORIGIN:$ORIGIN/..");
    } else if cfg!(target_os = "macos") {
        println!("cargo:rustc-link-arg=-Wl,-rpath,@loader_path");
    }
    println!("cargo:rerun-if-env-changed=DEP_DUCKDB_LIB_DIR");
    println!("cargo:rerun-if-env-changed=DEP_DUCKDB_INCLUDE");
}
