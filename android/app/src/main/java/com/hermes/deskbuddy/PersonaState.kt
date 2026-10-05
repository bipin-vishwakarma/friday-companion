package com.hermes.deskbuddy

enum class PersonaState {
    IDLE,
    LISTENING,
    THINKING,
    PLANNING,
    EXECUTING,
    SPEAKING,
    SUCCESS,
    WARNING,
    ERROR,
    PC_OFFLINE,
    PC_BOOTING,
    CONNECTING,
    HERMES_STARTING,
    OMNIROUTE_STARTING,
    UPDATING;

    fun label(): String = when (this) {
        IDLE             -> "READY"
        LISTENING        -> "LISTENING"
        THINKING         -> "THINKING"
        PLANNING         -> "PLANNING"
        EXECUTING        -> "EXECUTING"
        SPEAKING         -> "SPEAKING"
        SUCCESS          -> "DONE"
        WARNING          -> "WARNING"
        ERROR            -> "ERROR"
        PC_OFFLINE       -> "PC OFFLINE"
        PC_BOOTING       -> "PC BOOTING"
        CONNECTING       -> "CONNECTING"
        HERMES_STARTING  -> "HERMES STARTING"
        OMNIROUTE_STARTING -> "OMNIROUTE STARTING"
        UPDATING         -> "UPDATING"
    }
}
