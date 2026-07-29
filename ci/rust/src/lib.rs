include!("generated_api.rs");

pub mod imports {
    pub use serde;
    pub use bitfield_struct;
    pub use shvproto;
    pub use shvrpc;
    pub use shvclient;

    #[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
    pub struct CustomTimestamp;
    pub mod api {
    }
    pub mod nodes {
        pub struct ConfigNode;
        impl ConfigNode {
            pub async fn set_configuration(&self, _: shvrpc::RpcMessage, _: crate::Configuration, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!()
            }

            pub async fn get_logs(&self, _: shvrpc::RpcMessage, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!();
            }

            pub async fn get_optional_config(&self, _: shvrpc::RpcMessage, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!();
            }

            pub async fn set_optional_param(&self, _: shvrpc::RpcMessage, _: Option<crate::Configuration>, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!();
            }
        }
        pub struct IdentityNode;
        impl IdentityNode {
            pub async fn get_identity(&self, _: shvrpc::RpcMessage, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!();
            }
        }
        pub struct LogNode;
        impl LogNode {
            pub async fn get_logs(&self, _: shvrpc::RpcMessage, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!()
            }

            pub async fn delete_logs(&self, _: shvrpc::RpcMessage, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!()
            }
        }
        pub struct RootDevice;
        impl RootDevice {
            pub async fn get_device_status(&self, _: shvrpc::RpcMessage, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!()
            }
            pub async fn reboot_device(&self, _: shvrpc::RpcMessage, _: String, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!()
            }
        }
        pub struct SensorNode;
        impl SensorNode {
            pub async fn get_sensor_measurement(&self, _: shvrpc::RpcMessage, _: String, _: shvclient::ClientCommandSender) -> Option<Result<(), shvrpc::rpcmessage::RpcError>> {
                unimplemented!()
            }
        }
    }
}
