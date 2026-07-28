pub mod imports {
    pub use serde;
    pub use bitfield_struct;
    pub use shvproto;
    pub use shvrpc;
    pub use shvclient;
}

include!("../generated_api.rs");
