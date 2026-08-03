#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#ifdef _WIN32
#define TH06_EXPORT extern "C" __declspec(dllexport)
#else
#define TH06_EXPORT extern "C"
#endif

namespace {

struct Aabb {
    float left;
    float top;
    float right;
    float bottom;
};

struct LaserHazard {
    float originX;
    float originY;
    float angle;
    float centerOffset;
    float sizeX;
    float sizeY;
};

struct SafeResult {
    std::int32_t safe;
    float clearance;
    float finalX;
    float finalY;
};

struct Direction {
    std::int32_t dx;
    std::int32_t dy;
};

struct ControlAction {
    Direction direction;
    bool focused;
};

constexpr std::int32_t kFocusedActionCount = 9;
constexpr std::int32_t kControlActionCount = 18;
constexpr ControlAction kActions[kControlActionCount] = {
    {{0, 0}, true}, {{0, -1}, true}, {{0, 1}, true},
    {{-1, 0}, true}, {{1, 0}, true}, {{-1, -1}, true},
    {{1, -1}, true}, {{-1, 1}, true}, {{1, 1}, true},
    {{0, 0}, false}, {{0, -1}, false}, {{0, 1}, false},
    {{-1, 0}, false}, {{1, 0}, false}, {{-1, -1}, false},
    {{1, -1}, false}, {{-1, 1}, false}, {{1, 1}, false},
};
constexpr std::uint16_t kActionMasks[kControlActionCount] = {
    0x04U, 0x14U, 0x24U, 0x44U, 0x84U,
    0x54U, 0x94U, 0x64U, 0xA4U,
    0x00U, 0x10U, 0x20U, 0x40U, 0x80U,
    0x50U, 0x90U, 0x60U, 0xA0U,
};
constexpr std::uint16_t kControlBits[5] = {
    0x20U, 0x04U, 0x40U, 0x80U, 0x10U,
};
constexpr std::int32_t kDelays[4] = {0, 1, 2, 3};
constexpr std::int32_t kExtendedDelays[5] = {0, 1, 2, 3, 4};

using PolicyClock = std::chrono::steady_clock;
thread_local bool gPolicyDeadlineActive = false;
thread_local PolicyClock::time_point gPolicyDeadline;
thread_local bool gTerminalCountsOnly = false;
thread_local std::int32_t gTerminalContinuationLength = 0;
thread_local std::int32_t gTerminalProgressiveMinimumHorizon = 0;
thread_local std::int32_t* gTerminalProgressiveCompletedHorizon = nullptr;

bool policyDeadlineExpired() {
    return gPolicyDeadlineActive && PolicyClock::now() >= gPolicyDeadline;
}

ControlAction actionFromInput(std::uint16_t mask) {
    ControlAction result{{0, 0}, (mask & 0x04U) != 0U};
    if ((mask & 0x10U) != 0U) {
        result.direction.dy = -1;
        if ((mask & 0x40U) != 0U) result.direction.dx = -1;
        if ((mask & 0x80U) != 0U) result.direction.dx = 1;
    } else if ((mask & 0x20U) != 0U) {
        result.direction.dy = 1;
        if ((mask & 0x40U) != 0U) result.direction.dx = -1;
        if ((mask & 0x80U) != 0U) result.direction.dx = 1;
    } else {
        if ((mask & 0x40U) != 0U) result.direction.dx = -1;
        if ((mask & 0x80U) != 0U) result.direction.dx = 1;
    }
    return result;
}

bool sameAction(ControlAction left, ControlAction right) {
    return left.direction.dx == right.direction.dx
        && left.direction.dy == right.direction.dy
        && left.focused == right.focused;
}

std::int32_t transitionActions(
    std::uint16_t currentMask,
    std::uint16_t targetMask,
    ControlAction output[5]
) {
    currentMask &= 0xF4U;
    targetMask &= 0xF4U;
    std::uint16_t prefixMask = currentMask;
    const ControlAction current = actionFromInput(currentMask);
    const ControlAction target = actionFromInput(targetMask);
    std::int32_t count = 0;
    const auto append = [&](ControlAction prefix) {
        if (sameAction(prefix, current) || sameAction(prefix, target)) return;
        for (std::int32_t index = 0; index < count; ++index) {
            if (sameAction(prefix, output[index])) return;
        }
        output[count++] = prefix;
    };
    // Keyboard::_sync sorts control key names as down, focus, left, right, up,
    // publishing every release before every press in one SendInput batch.
    for (const std::uint16_t bit : kControlBits) {
        if ((currentMask & bit) != 0U && (targetMask & bit) == 0U) {
            prefixMask &= ~bit;
            append(actionFromInput(prefixMask));
        }
    }
    for (const std::uint16_t bit : kControlBits) {
        if ((targetMask & bit) != 0U && (currentMask & bit) == 0U) {
            prefixMask |= bit;
            append(actionFromInput(prefixMask));
        }
    }
    return count;
}

ControlAction scheduledAction(
    std::int32_t frame,
    std::int32_t delay,
    ControlAction current,
    ControlAction target,
    const ControlAction* transition
) {
    if (transition != nullptr) {
        if (frame < delay) return current;
        if (frame == delay) return *transition;
        return target;
    }
    return frame <= delay ? current : target;
}

void stepPlayer(
    float& x,
    float& y,
    ControlAction action,
    float normalCardinal,
    float focusCardinal,
    float normalDiagonal,
    float focusDiagonal
) {
    const bool diagonal = action.direction.dx != 0 && action.direction.dy != 0;
    const float speed = action.focused
        ? (diagonal ? focusDiagonal : focusCardinal)
        : (diagonal ? normalDiagonal : normalCardinal);
    x = std::clamp(
        x + static_cast<float>(action.direction.dx) * speed, 8.0F, 376.0F
    );
    y = std::clamp(
        y + static_cast<float>(action.direction.dy) * speed, 16.0F, 432.0F
    );
}

float signedClearance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const Aabb& hazard
) {
    const float gapX = std::max(
        hazard.left - (playerX + playerHalfWidth),
        (playerX - playerHalfWidth) - hazard.right
    );
    const float gapY = std::max(
        hazard.top - (playerY + playerHalfHeight),
        (playerY - playerHalfHeight) - hazard.bottom
    );
    if (gapX <= 0.0F && gapY <= 0.0F) return std::max(gapX, gapY);
    return std::hypot(std::max(0.0F, gapX), std::max(0.0F, gapY));
}

bool withinMargin(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const Aabb& hazard,
    float collisionMargin
) {
    const float gapX = std::max(
        hazard.left - (playerX + playerHalfWidth),
        (playerX - playerHalfWidth) - hazard.right
    );
    const float gapY = std::max(
        hazard.top - (playerY + playerHalfHeight),
        (playerY - playerHalfHeight) - hazard.bottom
    );
    const float positiveX = std::max(0.0F, gapX);
    const float positiveY = std::max(0.0F, gapY);
    return positiveX * positiveX + positiveY * positiveY
        <= collisionMargin * collisionMargin;
}

float signedLaserClearance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const LaserHazard& laser
) {
    const float dx = playerX - laser.originX;
    const float dy = playerY - laser.originY;
    const float sine = std::sin(laser.angle);
    const float cosine = std::cos(laser.angle);
    const float localX = cosine * dx + sine * dy;
    const float localY = cosine * dy - sine * dx;
    const Aabb box{
        laser.centerOffset - laser.sizeX / 2.0F,
        -laser.sizeY / 2.0F,
        laser.centerOffset + laser.sizeX / 2.0F,
        laser.sizeY / 2.0F,
    };
    return signedClearance(localX, localY, playerHalfWidth, playerHalfHeight, box);
}

bool withinLaserMargin(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    const LaserHazard& laser,
    float collisionMargin
) {
    const float dx = playerX - laser.originX;
    const float dy = playerY - laser.originY;
    const float sine = std::sin(laser.angle);
    const float cosine = std::cos(laser.angle);
    const float localX = cosine * dx + sine * dy;
    const float localY = cosine * dy - sine * dx;
    const Aabb box{
        laser.centerOffset - laser.sizeX / 2.0F,
        -laser.sizeY / 2.0F,
        laser.centerOffset + laser.sizeX / 2.0F,
        laser.sizeY / 2.0F,
    };
    return withinMargin(
        localX,
        localY,
        playerHalfWidth,
        playerHalfHeight,
        box,
        collisionMargin
    );
}

bool safeAtFrame(
    float x,
    float y,
    float playerHalfWidth,
    float playerHalfHeight,
    std::int32_t frameIndex,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    float* clearance
) {
    const std::uint32_t bulletStart = bulletOffsets[frameIndex];
    const std::uint32_t bulletEnd = bulletOffsets[frameIndex + 1];
    for (std::uint32_t index = bulletStart; index < bulletEnd; ++index) {
        if (clearance == nullptr) {
            if (withinMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                bullets[index],
                collisionMargin
            )) return false;
            continue;
        }
        const float value = signedClearance(
            x, y, playerHalfWidth, playerHalfHeight, bullets[index]
        );
        *clearance = std::min(*clearance, value);
        if (value <= collisionMargin) return false;
    }
    const std::uint32_t laserStart = laserOffsets[frameIndex];
    const std::uint32_t laserEnd = laserOffsets[frameIndex + 1];
    for (std::uint32_t index = laserStart; index < laserEnd; ++index) {
        if (clearance == nullptr) {
            if (withinLaserMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                lasers[index],
                collisionMargin
            )) return false;
            continue;
        }
        const float value = signedLaserClearance(
            x, y, playerHalfWidth, playerHalfHeight, lasers[index]
        );
        *clearance = std::min(*clearance, value);
        if (value <= collisionMargin) return false;
    }
    return true;
}

std::uint64_t positionKey(float x, float y) {
    std::uint32_t xBits;
    std::uint32_t yBits;
    std::memcpy(&xBits, &x, sizeof(xBits));
    std::memcpy(&yBits, &y, sizeof(yBits));
    return (static_cast<std::uint64_t>(xBits) << 32U) | yBits;
}

void positionFromKey(std::uint64_t key, float& x, float& y) {
    const std::uint32_t xBits = static_cast<std::uint32_t>(key >> 32U);
    const std::uint32_t yBits = static_cast<std::uint32_t>(key);
    std::memcpy(&x, &xBits, sizeof(x));
    std::memcpy(&y, &yBits, sizeof(y));
}

}  // namespace

TH06_EXPORT std::int32_t th06_certify_actions(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    SafeResult* output,
    SafeResult* ageZeroOutput,
    SafeResult* extendedOutput
) {
    if (
        horizon <= 0 || horizon > 64 || bulletOffsets == nullptr ||
        laserOffsets == nullptr || output == nullptr || ageZeroOutput == nullptr
    ) {
        return -1;
    }
    const ControlAction current = actionFromInput(inputMask);

    for (std::int32_t actionIndex = 0; actionIndex < kControlActionCount; ++actionIndex) {
        if ((candidateMask & (1U << actionIndex)) == 0U) {
            output[actionIndex] = SafeResult{0, 0.0F, playerX, playerY};
            ageZeroOutput[actionIndex] = SafeResult{0, 0.0F, playerX, playerY};
            if (extendedOutput != nullptr) {
                extendedOutput[actionIndex] = SafeResult{0, 0.0F, playerX, playerY};
            }
            continue;
        }
        SafeResult result{1, 999.0F, playerX, playerY};
        SafeResult ageZeroResult{0, 0.0F, playerX, playerY};
        SafeResult hardResult{0, 0.0F, playerX, playerY};
        ControlAction transitions[5];
        const std::int32_t transitionCount = transitionActions(
            inputMask, kActionMasks[actionIndex], transitions
        );
        const std::int32_t delayCount = extendedOutput == nullptr ? 4 : 5;
        for (std::int32_t delayIndex = 0; delayIndex < delayCount; ++delayIndex) {
            const std::int32_t delay = kExtendedDelays[delayIndex];
            float normalFinalX = playerX;
            float normalFinalY = playerY;
            const std::int32_t branchCount = 1 + (delay > 0 ? transitionCount : 0);
            for (std::int32_t branch = 0; branch < branchCount; ++branch) {
                const ControlAction* transition = branch == 0
                    ? nullptr
                    : &transitions[branch - 1];
                float x = playerX;
                float y = playerY;
                for (std::int32_t frame = 1; frame <= horizon; ++frame) {
                    stepPlayer(
                        x,
                        y,
                        scheduledAction(
                            frame, delay, current, kActions[actionIndex], transition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                    if (!safeAtFrame(
                        x,
                        y,
                        playerHalfWidth,
                        playerHalfHeight,
                        frame - 1,
                        bulletOffsets,
                        bullets,
                        laserOffsets,
                        lasers,
                        collisionMargin,
                        &result.clearance
                    )) {
                        result.safe = 0;
                        break;
                    }
                }
                if (result.safe == 0) break;
                if (branch == 0) {
                    normalFinalX = x;
                    normalFinalY = y;
                }
            }
            if (delay == kDelays[2]) {
                ageZeroResult = result;
                ageZeroResult.finalX = normalFinalX;
                ageZeroResult.finalY = normalFinalY;
            }
            if (result.safe == 0) break;
            if (delay == kDelays[3]) {
                hardResult = result;
                hardResult.finalX = normalFinalX;
                hardResult.finalY = normalFinalY;
            }
            if (delay == kExtendedDelays[4]) {
                result.finalX = normalFinalX;
                result.finalY = normalFinalY;
            }
        }
        output[actionIndex] = hardResult;
        ageZeroOutput[actionIndex] = ageZeroResult;
        if (extendedOutput != nullptr) {
            extendedOutput[actionIndex] = result;
        }
    }
    return 0;
}

// This is a proposal score only. candidateMask must already come from the
// hard authority; the result can rank those candidates but cannot add one.
TH06_EXPORT std::int32_t th06_replanning_scores(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t split,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    std::int32_t* output
) {
    if (
        split <= 0 || horizon <= split || horizon > 64 ||
        bulletOffsets == nullptr || laserOffsets == nullptr || output == nullptr
    ) {
        return -1;
    }
    const ControlAction current = actionFromInput(inputMask);
    // Delivery and transition branches revisit the same small movement
    // lattice thousands of times.  Cache exact float positions per future
    // frame so each dense hazard slice is scanned once without changing the
    // conservative branch set or its scores.
    std::array<std::unordered_map<std::uint64_t, bool>, 64> safetyCache;
    constexpr std::int32_t kCellSize = 32;
    constexpr std::int32_t kGridWidth = 12;
    constexpr std::int32_t kGridHeight = 14;
    constexpr std::int32_t kGridCells = kGridWidth * kGridHeight;
    std::array<std::array<std::vector<std::uint32_t>, kGridCells>, 64>
        bulletGrid;
    const auto clampCellX = [](std::int32_t value) {
        return std::clamp(value, 0, kGridWidth - 1);
    };
    const auto clampCellY = [](std::int32_t value) {
        return std::clamp(value, 0, kGridHeight - 1);
    };
    for (std::int32_t frame = split; frame < horizon; ++frame) {
        for (
            std::uint32_t index = bulletOffsets[frame];
            index < bulletOffsets[frame + 1];
            ++index
        ) {
            const Aabb& hazard = bullets[index];
            const std::int32_t left = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.left - playerHalfWidth - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t right = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.right + playerHalfWidth + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t top = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.top - playerHalfHeight - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t bottom = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.bottom + playerHalfHeight + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            for (std::int32_t cellY = top; cellY <= bottom; ++cellY) {
                for (std::int32_t cellX = left; cellX <= right; ++cellX) {
                    bulletGrid[frame][cellY * kGridWidth + cellX].push_back(index);
                }
            }
        }
    }
    const auto spatialSafeAtFrame = [&](float x, float y, std::int32_t frame) {
        auto& frameCache = safetyCache[frame];
        const std::uint64_t key = positionKey(x, y);
        const auto found = frameCache.find(key);
        if (found != frameCache.end()) return found->second;
        const std::int32_t cellX = clampCellX(static_cast<std::int32_t>(
            std::floor(x / static_cast<float>(kCellSize))
        ));
        const std::int32_t cellY = clampCellY(static_cast<std::int32_t>(
            std::floor(y / static_cast<float>(kCellSize))
        ));
        bool safe = true;
        for (const std::uint32_t index : bulletGrid[frame][
            cellY * kGridWidth + cellX
        ]) {
            if (withinMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                bullets[index],
                collisionMargin
            )) {
                safe = false;
                break;
            }
        }
        if (safe) {
            for (
                std::uint32_t index = laserOffsets[frame];
                index < laserOffsets[frame + 1];
                ++index
            ) {
                if (withinLaserMargin(
                    x,
                    y,
                    playerHalfWidth,
                    playerHalfHeight,
                    lasers[index],
                    collisionMargin
                )) {
                    safe = false;
                    break;
                }
            }
        }
        frameCache.emplace(key, safe);
        return safe;
    };
    for (std::int32_t firstIndex = 0; firstIndex < kControlActionCount; ++firstIndex) {
        output[firstIndex] = 0;
        if ((candidateMask & (1U << firstIndex)) == 0U) continue;
        ControlAction firstTransitions[5];
        const std::int32_t firstTransitionCount = transitionActions(
            inputMask, kActionMasks[firstIndex], firstTransitions
        );
        std::int32_t worstBranchCount = kFocusedActionCount;
        for (const std::int32_t firstDelay : kDelays) {
            const std::int32_t firstBranchCount = 1 + (
                firstDelay > 0 ? firstTransitionCount : 0
            );
            for (std::int32_t firstBranch = 0; firstBranch < firstBranchCount; ++firstBranch) {
                const ControlAction* firstTransition = firstBranch == 0
                    ? nullptr
                    : &firstTransitions[firstBranch - 1];
                float splitX = playerX;
                float splitY = playerY;
                for (std::int32_t frame = 1; frame <= split; ++frame) {
                    stepPlayer(
                        splitX,
                        splitY,
                        scheduledAction(
                            frame,
                            firstDelay,
                            current,
                            kActions[firstIndex],
                            firstTransition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                }
                std::int32_t continuationCount = 0;
                std::unordered_set<std::uint64_t> continuationStates;
                for (
                    std::int32_t secondIndex = 0;
                    secondIndex < kFocusedActionCount;
                    ++secondIndex
                ) {
                    ControlAction secondTransitions[5];
                    const std::int32_t secondTransitionCount = transitionActions(
                        kActionMasks[firstIndex],
                        kActionMasks[secondIndex],
                        secondTransitions
                    );
                    bool survived = true;
                    float nominalFinalX = splitX;
                    float nominalFinalY = splitY;
                    for (const std::int32_t secondDelay : kDelays) {
                        const std::int32_t secondBranchCount = 1 + (
                            secondDelay > 0 ? secondTransitionCount : 0
                        );
                        for (
                            std::int32_t secondBranch = 0;
                            secondBranch < secondBranchCount;
                            ++secondBranch
                        ) {
                            const ControlAction* secondTransition = secondBranch == 0
                                ? nullptr
                                : &secondTransitions[secondBranch - 1];
                            float x = splitX;
                            float y = splitY;
                            for (std::int32_t frame = split + 1; frame <= horizon; ++frame) {
                                const std::int32_t elapsed = frame - split;
                                stepPlayer(
                                    x,
                                    y,
                                    scheduledAction(
                                        elapsed,
                                        secondDelay,
                                        kActions[firstIndex],
                                        kActions[secondIndex],
                                        secondTransition
                                    ),
                                    normalSpeed,
                                    focusSpeed,
                                    normalDiagonalSpeed,
                                    focusDiagonalSpeed
                                );
                                if (!spatialSafeAtFrame(x, y, frame - 1)) {
                                    survived = false;
                                    break;
                                }
                            }
                            if (!survived) break;
                            if (secondDelay == 0 && secondBranch == 0) {
                                nominalFinalX = x;
                                nominalFinalY = y;
                            }
                        }
                        if (!survived) break;
                    }
                    if (
                        survived
                        && continuationStates.insert(positionKey(
                            nominalFinalX, nominalFinalY
                        )).second
                    ) {
                        continuationCount++;
                    }
                }
                worstBranchCount = std::min(worstBranchCount, continuationCount);
                if (worstBranchCount == 0) break;
            }
            if (worstBranchCount == 0) break;
        }
        output[firstIndex] = worstBranchCount;
    }
    return 0;
}

// Proposal-only nominal policy volume. The first segment retains every
// physical delivery branch. Later segments count safe MPC policies under
// nominal pickup; actual execution is still re-certified by Hard-4.
TH06_EXPORT std::int32_t th06_nominal_policy_counts(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    std::int32_t* output
) {
    if (
        segmentLength <= 0 || horizon <= segmentLength || horizon > 64 ||
        bulletOffsets == nullptr || laserOffsets == nullptr || output == nullptr
    ) {
        return -1;
    }
    bool timedOut = false;
    const auto deadlineExpired = [&]() {
        if (!policyDeadlineExpired()) return false;
        timedOut = true;
        return true;
    };
    if (deadlineExpired()) return 1;
    std::array<std::unordered_map<std::uint64_t, bool>, 64> safetyCache;
    constexpr std::int32_t kCellSize = 32;
    constexpr std::int32_t kGridWidth = 12;
    constexpr std::int32_t kGridHeight = 14;
    constexpr std::int32_t kGridCells = kGridWidth * kGridHeight;
    std::array<std::array<std::vector<std::uint32_t>, kGridCells>, 64>
        bulletGrid;
    const auto clampCellX = [](std::int32_t value) {
        return std::clamp(value, 0, kGridWidth - 1);
    };
    const auto clampCellY = [](std::int32_t value) {
        return std::clamp(value, 0, kGridHeight - 1);
    };
    for (std::int32_t frame = 0; frame < horizon; ++frame) {
        if (deadlineExpired()) return 1;
        for (
            std::uint32_t index = bulletOffsets[frame];
            index < bulletOffsets[frame + 1];
            ++index
        ) {
            const Aabb& hazard = bullets[index];
            const std::int32_t left = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.left - playerHalfWidth - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t right = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.right + playerHalfWidth + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t top = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.top - playerHalfHeight - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t bottom = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.bottom + playerHalfHeight + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            for (std::int32_t cellY = top; cellY <= bottom; ++cellY) {
                for (std::int32_t cellX = left; cellX <= right; ++cellX) {
                    bulletGrid[frame][cellY * kGridWidth + cellX].push_back(index);
                }
            }
        }
    }
    const auto spatialSafeAtFrame = [&](float x, float y, std::int32_t frame) {
        if (deadlineExpired()) return false;
        auto& frameCache = safetyCache[frame];
        const std::uint64_t key = positionKey(x, y);
        const auto found = frameCache.find(key);
        if (found != frameCache.end()) return found->second;
        const std::int32_t cellX = clampCellX(static_cast<std::int32_t>(
            std::floor(x / static_cast<float>(kCellSize))
        ));
        const std::int32_t cellY = clampCellY(static_cast<std::int32_t>(
            std::floor(y / static_cast<float>(kCellSize))
        ));
        bool safe = true;
        for (const std::uint32_t index : bulletGrid[frame][
            cellY * kGridWidth + cellX
        ]) {
            if (withinMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                bullets[index],
                collisionMargin
            )) {
                safe = false;
                break;
            }
        }
        if (safe) {
            for (
                std::uint32_t index = laserOffsets[frame];
                index < laserOffsets[frame + 1];
                ++index
            ) {
                if (withinLaserMargin(
                    x,
                    y,
                    playerHalfWidth,
                    playerHalfHeight,
                    lasers[index],
                    collisionMargin
                )) {
                    safe = false;
                    break;
                }
            }
        }
        frameCache.emplace(key, safe);
        return safe;
    };
    std::array<std::unordered_map<std::uint64_t, std::int32_t>, 65>
        viabilityCache;

    const auto bestFrom = [&](auto&& self, float startX, float startY,
                              std::int32_t startFrame) -> std::int32_t {
        if (deadlineExpired()) return 0;
        if (startFrame >= horizon) return 1;
        auto& memo = viabilityCache[startFrame];
        const std::uint64_t key = positionKey(startX, startY);
        const auto found = memo.find(key);
        if (found != memo.end()) return found->second;

        const std::int32_t endFrame = std::min(
            horizon, startFrame + segmentLength
        );
        std::int32_t total = 0;
        std::array<std::uint64_t, kFocusedActionCount> nextStates{};
        std::int32_t nextStateCount = 0;
        for (std::int32_t nextIndex = 0; nextIndex < kFocusedActionCount; ++nextIndex) {
            if (deadlineExpired()) return 0;
            float x = startX;
            float y = startY;
            bool survived = true;
            for (
                std::int32_t frame = startFrame + 1;
                frame <= endFrame;
                ++frame
            ) {
                stepPlayer(
                    x,
                    y,
                    kActions[nextIndex],
                    normalSpeed,
                    focusSpeed,
                    normalDiagonalSpeed,
                    focusDiagonalSpeed
                );
                if (!spatialSafeAtFrame(x, y, frame - 1)) {
                    survived = false;
                    break;
                }
            }
            if (survived) {
                const std::uint64_t nextKey = positionKey(x, y);
                if (
                    std::find(
                        nextStates.begin(),
                        nextStates.begin() + nextStateCount,
                        nextKey
                    ) != nextStates.begin() + nextStateCount
                ) {
                    continue;
                }
                nextStates[nextStateCount++] = nextKey;
                const std::int32_t branchCount = endFrame == horizon
                    ? 1
                    : self(self, x, y, endFrame);
                if (timedOut) return 0;
                total = branchCount > INT32_MAX - total
                    ? INT32_MAX
                    : total + branchCount;
            }
        }
        memo.emplace(key, total);
        return total;
    };

    const ControlAction current = actionFromInput(inputMask);
    for (std::int32_t firstIndex = 0; firstIndex < kControlActionCount; ++firstIndex) {
        if (deadlineExpired()) return 1;
        output[firstIndex] = 0;
        if ((candidateMask & (1U << firstIndex)) == 0U) continue;
        ControlAction transitions[5];
        const std::int32_t transitionCount = transitionActions(
            inputMask, kActionMasks[firstIndex], transitions
        );
        std::int32_t worst = INT32_MAX;
        for (const std::int32_t delay : kDelays) {
            if (deadlineExpired()) return 1;
            const std::int32_t branchCount = 1 + (
                delay > 0 ? transitionCount : 0
            );
            for (std::int32_t branch = 0; branch < branchCount; ++branch) {
                if (deadlineExpired()) return 1;
                const ControlAction* transition = branch == 0
                    ? nullptr
                    : &transitions[branch - 1];
                float x = playerX;
                float y = playerY;
                bool survived = true;
                for (std::int32_t frame = 1; frame <= segmentLength; ++frame) {
                    stepPlayer(
                        x,
                        y,
                        scheduledAction(
                            frame, delay, current, kActions[firstIndex], transition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                    if (!spatialSafeAtFrame(x, y, frame - 1)) {
                        survived = false;
                        break;
                    }
                }
                const std::int32_t branchValue = survived
                    ? bestFrom(bestFrom, x, y, segmentLength)
                    : 0;
                if (timedOut) return 1;
                worst = std::min(worst, branchValue);
            }
        }
        output[firstIndex] = worst == INT32_MAX ? 0 : worst;
    }
    return 0;
}

// The result is all-or-nothing: status 1 means the deadline expired and the
// caller must discard every output slot. Hard authority never uses this path.
TH06_EXPORT std::int32_t th06_nominal_policy_counts_budgeted(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    double budgetMs,
    std::int32_t* output
) {
    if (!(budgetMs > 0.0) || !std::isfinite(budgetMs)) return -1;
    const bool previousActive = gPolicyDeadlineActive;
    const PolicyClock::time_point previousDeadline = gPolicyDeadline;
    gPolicyDeadlineActive = true;
    gPolicyDeadline = PolicyClock::now() +
        std::chrono::duration_cast<PolicyClock::duration>(
            std::chrono::duration<double, std::milli>(budgetMs)
        );
    const std::int32_t status = th06_nominal_policy_counts(
        playerX,
        playerY,
        playerHalfWidth,
        playerHalfHeight,
        normalSpeed,
        focusSpeed,
        normalDiagonalSpeed,
        focusDiagonalSpeed,
        inputMask,
        segmentLength,
        horizon,
        candidateMask,
        bulletOffsets,
        bullets,
        laserOffsets,
        lasers,
        collisionMargin,
        output
    );
    gPolicyDeadline = previousDeadline;
    gPolicyDeadlineActive = previousActive;
    return status;
}

// Proposal-only global target/local path guidance. Terminal positions are
// deduplicated across every nominal continuation path. The free-space target
// is selected only inside a caller-supplied Hard first-action branch; a later
// call can rank Hard actions by robust distance to that fixed target/deadline.
TH06_EXPORT std::int32_t th06_terminal_guidance(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    float targetX,
    float targetY,
    std::int32_t* terminalCountOutput,
    float* freeClearanceOutput,
    float* freeTargetXOutput,
    float* freeTargetYOutput,
    float* targetDistanceSquaredOutput
) {
    if (
        segmentLength <= 0 || horizon < segmentLength || horizon > 64 ||
        bulletOffsets == nullptr || laserOffsets == nullptr ||
        terminalCountOutput == nullptr || freeClearanceOutput == nullptr ||
        freeTargetXOutput == nullptr || freeTargetYOutput == nullptr ||
        targetDistanceSquaredOutput == nullptr
    ) {
        return -1;
    }
    bool timedOut = false;
    const auto deadlineExpired = [&]() {
        if (!policyDeadlineExpired()) return false;
        timedOut = true;
        return true;
    };
    if (deadlineExpired()) return 1;

    // Terminal reachability revisits the same movement lattice across many
    // first-action delivery branches.  Use the same exact-position cache and
    // conservative bullet grid as the policy-volume kernel so each dense
    // hazard slice is not scanned once per aliased reachable state.
    std::vector<std::unordered_map<std::uint64_t, bool>> safetyCache(horizon);
    constexpr std::int32_t kCellSize = 32;
    constexpr std::int32_t kGridWidth = 12;
    constexpr std::int32_t kGridHeight = 14;
    constexpr std::int32_t kGridCells = kGridWidth * kGridHeight;
    std::vector<std::array<std::vector<std::uint32_t>, kGridCells>>
        bulletGrid(horizon);
    const auto clampCellX = [](std::int32_t value) {
        return std::clamp(value, 0, kGridWidth - 1);
    };
    const auto clampCellY = [](std::int32_t value) {
        return std::clamp(value, 0, kGridHeight - 1);
    };
    for (std::int32_t frame = 0; frame < horizon; ++frame) {
        if (deadlineExpired()) return 1;
        for (
            std::uint32_t index = bulletOffsets[frame];
            index < bulletOffsets[frame + 1];
            ++index
        ) {
            const Aabb& hazard = bullets[index];
            const std::int32_t left = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.left - playerHalfWidth - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t right = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.right + playerHalfWidth + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t top = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.top - playerHalfHeight - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t bottom = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.bottom + playerHalfHeight + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            for (std::int32_t cellY = top; cellY <= bottom; ++cellY) {
                for (std::int32_t cellX = left; cellX <= right; ++cellX) {
                    bulletGrid[frame][cellY * kGridWidth + cellX].push_back(
                        index
                    );
                }
            }
        }
    }
    const auto spatialSafeAtFrame = [&](float x, float y, std::int32_t frame) {
        // Counts-only propagation polls at every reachable-state boundary.
        // Re-reading the Windows steady clock at every point along a four-
        // frame segment costs more than the spatial collision query itself.
        if (!gTerminalCountsOnly && deadlineExpired()) return false;
        auto& frameCache = safetyCache[frame];
        const std::uint64_t key = positionKey(x, y);
        if (!gTerminalCountsOnly) {
            const auto found = frameCache.find(key);
            if (found != frameCache.end()) return found->second;
        }
        const std::int32_t cellX = clampCellX(static_cast<std::int32_t>(
            std::floor(x / static_cast<float>(kCellSize))
        ));
        const std::int32_t cellY = clampCellY(static_cast<std::int32_t>(
            std::floor(y / static_cast<float>(kCellSize))
        ));
        bool safe = true;
        for (const std::uint32_t index : bulletGrid[frame][
            cellY * kGridWidth + cellX
        ]) {
            if (withinMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                bullets[index],
                collisionMargin
            )) {
                safe = false;
                break;
            }
        }
        if (safe) {
            for (
                std::uint32_t index = laserOffsets[frame];
                index < laserOffsets[frame + 1];
                ++index
            ) {
                if (withinLaserMargin(
                    x,
                    y,
                    playerHalfWidth,
                    playerHalfHeight,
                    lasers[index],
                    collisionMargin
                )) {
                    safe = false;
                    break;
                }
            }
        }
        if (!gTerminalCountsOnly) frameCache.emplace(key, safe);
        return safe;
    };

    const std::int32_t continuationLength = (
        gTerminalContinuationLength > 0
        ? gTerminalContinuationLength
        : segmentLength
    );
    const bool progressiveCounts = (
        gTerminalCountsOnly
        && gTerminalProgressiveCompletedHorizon != nullptr
    );

    if (gTerminalCountsOnly) {
        // Propagate every distinct post-delivery origin together.  Each
        // reachable position carries the origins that can reach it; merging
        // equal positions unions those labels.  Counting terminal labels is
        // therefore exactly the same per-origin set cardinality as separate
        // forward searches, while shared reachable states are expanded once.
        constexpr std::int32_t kMaxBranchesPerAction = 19;
        constexpr std::int32_t kMaxOrigins =
            kControlActionCount * kMaxBranchesPerAction;
        using OriginBits = std::uint64_t;
        struct OriginPosition {
            std::uint64_t key;
        };
        struct LabeledPosition {
            std::uint64_t key;
            OriginBits origins;
        };

        std::array<std::vector<std::int32_t>, kControlActionCount>
            branchOrigins;
        std::vector<OriginPosition> origins;
        origins.reserve(kMaxOrigins);
        std::unordered_map<std::uint64_t, std::int32_t> originByPosition;
        originByPosition.reserve(kMaxOrigins);
        const auto registerOrigin = [&](float x, float y) {
            const std::uint64_t key = positionKey(x, y);
            const auto found = originByPosition.find(key);
            if (found != originByPosition.end()) return found->second;
            const std::int32_t index = static_cast<std::int32_t>(
                origins.size()
            );
            origins.push_back(OriginPosition{key});
            originByPosition.emplace(key, index);
            return index;
        };

        const ControlAction current = actionFromInput(inputMask);
        for (
            std::int32_t firstIndex = 0;
            firstIndex < kControlActionCount;
            ++firstIndex
        ) {
            if (deadlineExpired()) return 1;
            terminalCountOutput[firstIndex] = 0;
            if ((candidateMask & (1U << firstIndex)) == 0U) continue;
            ControlAction transitions[5];
            const std::int32_t transitionCount = transitionActions(
                inputMask, kActionMasks[firstIndex], transitions
            );
            for (const std::int32_t delay : kDelays) {
                const std::int32_t branchCount = 1 + (
                    delay > 0 ? transitionCount : 0
                );
                for (
                    std::int32_t branch = 0;
                    branch < branchCount;
                    ++branch
                ) {
                    if (deadlineExpired()) return 1;
                    const ControlAction* transition = branch == 0
                        ? nullptr
                        : &transitions[branch - 1];
                    float x = playerX;
                    float y = playerY;
                    bool survived = true;
                    for (
                        std::int32_t frame = 1;
                        frame <= segmentLength;
                        ++frame
                    ) {
                        stepPlayer(
                            x,
                            y,
                            scheduledAction(
                                frame,
                                delay,
                                current,
                                kActions[firstIndex],
                                transition
                            ),
                            normalSpeed,
                            focusSpeed,
                            normalDiagonalSpeed,
                            focusDiagonalSpeed
                        );
                        if (!spatialSafeAtFrame(x, y, frame - 1)) {
                            survived = false;
                            break;
                        }
                    }
                    branchOrigins[firstIndex].push_back(
                        survived ? registerOrigin(x, y) : -1
                    );
                }
            }
        }

        // The ordinary focused-action frontier has at most one machine word
        // of distinct post-delivery origins.  Use a compact label there; a
        // larger generic caller falls through to the exact per-origin search
        // below rather than truncating reachability.
        if (origins.size() <= 64) {
            std::uint32_t deadlinePoll = 0;
            const auto countsDeadlineExpired = [&]() {
                ++deadlinePoll;
                return (
                    (deadlinePoll & 0x0FU) == 0U
                    && deadlineExpired()
                );
            };
            std::array<float, kFocusedActionCount> focusedStepX{};
            std::array<float, kFocusedActionCount> focusedStepY{};
            for (
                std::int32_t actionIndex = 0;
                actionIndex < kFocusedActionCount;
                ++actionIndex
            ) {
                const ControlAction action = kActions[actionIndex];
                const bool diagonal = (
                    action.direction.dx != 0 && action.direction.dy != 0
                );
                const float speed = diagonal
                    ? focusDiagonalSpeed
                    : focusSpeed;
                focusedStepX[actionIndex] =
                    static_cast<float>(action.direction.dx) * speed;
                focusedStepY[actionIndex] =
                    static_cast<float>(action.direction.dy) * speed;
            }
            std::vector<LabeledPosition> states;
            states.reserve(origins.size());
            for (
                std::int32_t index = 0;
                index < static_cast<std::int32_t>(origins.size());
                ++index
            ) {
                const OriginBits labels = 1ULL << index;
                const auto& origin = origins[index];
                states.push_back(LabeledPosition{
                    origin.key, labels
                });
            }

            const auto publishCounts = [
                &states,
                &origins,
                &branchOrigins,
                &countsDeadlineExpired,
                &deadlineExpired,
                candidateMask,
                terminalCountOutput
            ](std::int32_t completedHorizon) {
                std::vector<std::int32_t> originCounts(
                    origins.size(), 0
                );
                for (const auto& state : states) {
                    if (countsDeadlineExpired()) return false;
                    std::uint64_t labels = state.origins;
                    while (labels != 0U) {
                        const std::uint32_t origin = (
                            static_cast<std::uint32_t>(
                                __builtin_ctzll(labels)
                            )
                        );
                        ++originCounts[origin];
                        labels &= labels - 1U;
                    }
                }
                if (deadlineExpired()) return false;
                std::array<std::int32_t, kControlActionCount> counts{};
                for (
                    std::int32_t firstIndex = 0;
                    firstIndex < kControlActionCount;
                    ++firstIndex
                ) {
                    if ((candidateMask & (1U << firstIndex)) == 0U) {
                        continue;
                    }
                    std::int32_t worstCount = INT32_MAX;
                    for (
                        const std::int32_t origin
                        : branchOrigins[firstIndex]
                    ) {
                        worstCount = std::min(
                            worstCount,
                            origin < 0 ? 0 : originCounts[origin]
                        );
                    }
                    counts[firstIndex] = (
                        worstCount == INT32_MAX ? 0 : worstCount
                    );
                }
                if (deadlineExpired()) return false;
                std::copy(
                    counts.begin(), counts.end(), terminalCountOutput
                );
                if (gTerminalProgressiveCompletedHorizon != nullptr) {
                    *gTerminalProgressiveCompletedHorizon = completedHorizon;
                }
                return true;
            };

            for (
                std::int32_t startFrame = segmentLength;
                startFrame < horizon;
                startFrame += continuationLength
            ) {
                const std::int32_t endFrame = std::min(
                    horizon, startFrame + continuationLength
                );
                if (states.empty()) {
                    if (progressiveCounts) {
                        if (!publishCounts(horizon)) return 1;
                    }
                    break;
                }
                const std::size_t generatedCapacity =
                    states.size() * kFocusedActionCount;
                std::size_t tableCapacity = 1;
                while (
                    tableCapacity
                    < generatedCapacity + generatedCapacity / 2
                ) {
                    tableCapacity *= 2;
                }
                std::vector<LabeledPosition> table(tableCapacity);
                const std::size_t tableMask = tableCapacity - 1;
                std::size_t uniqueCount = 0;
                for (const auto& state : states) {
                    if (countsDeadlineExpired()) return 1;
                    float startX;
                    float startY;
                    positionFromKey(state.key, startX, startY);
                    for (
                        std::int32_t actionIndex = 0;
                        actionIndex < kFocusedActionCount;
                        ++actionIndex
                    ) {
                        float x = startX;
                        float y = startY;
                        bool survived = true;
                        const bool deferEndpointSafety = (
                            continuationLength == 1
                        );
                        for (
                            std::int32_t frame = startFrame + 1;
                            frame <= endFrame;
                            ++frame
                        ) {
                            x = std::clamp(
                                x + focusedStepX[actionIndex],
                                8.0F,
                                376.0F
                            );
                            y = std::clamp(
                                y + focusedStepY[actionIndex],
                                16.0F,
                                432.0F
                            );
                            if (
                                !deferEndpointSafety
                                && !spatialSafeAtFrame(x, y, frame - 1)
                            ) {
                                survived = false;
                                break;
                            }
                        }
                        if (!survived) continue;
                        const std::uint64_t key = positionKey(x, y);
                        std::uint64_t mixed = key;
                        mixed ^= mixed >> 30U;
                        mixed *= 0xBF58476D1CE4E5B9ULL;
                        mixed ^= mixed >> 27U;
                        mixed *= 0x94D049BB133111EBULL;
                        mixed ^= mixed >> 31U;
                        std::size_t slotIndex = (
                            static_cast<std::size_t>(mixed) & tableMask
                        );
                        while (
                            table[slotIndex].key != 0U
                            && table[slotIndex].key != key
                        ) {
                            slotIndex = (slotIndex + 1) & tableMask;
                        }
                        if (table[slotIndex].key == key) {
                            if (table[slotIndex].origins != 0U) {
                                table[slotIndex].origins |= state.origins;
                            }
                            continue;
                        }
                        if (
                            deferEndpointSafety
                            && !spatialSafeAtFrame(x, y, endFrame - 1)
                        ) {
                            // Cache this unsafe endpoint for the rest of the
                            // layer.  A one-frame transition has no hidden
                            // intermediate path, so equal endpoints have the
                            // same collision result.
                            table[slotIndex].key = key;
                            continue;
                        }
                        if (table[slotIndex].key == 0U) {
                                table[slotIndex] = LabeledPosition{
                                    key, state.origins
                                };
                                ++uniqueCount;
                        }
                    }
                }
                if (deadlineExpired()) return 1;
                std::vector<LabeledPosition> nextStates;
                nextStates.reserve(uniqueCount);
                for (const auto& entry : table) {
                    if (entry.key != 0U && entry.origins != 0U) {
                        nextStates.push_back(entry);
                    }
                }
                states = std::move(nextStates);
                if (
                    progressiveCounts
                    && endFrame >= gTerminalProgressiveMinimumHorizon
                ) {
                    if (!publishCounts(endFrame)) return 1;
                    if (states.empty() && endFrame < horizon) {
                        *gTerminalProgressiveCompletedHorizon = horizon;
                        break;
                    }
                }
            }

            if (!progressiveCounts && !publishCounts(horizon)) return 1;
            return timedOut ? 1 : 0;
        }
        if (progressiveCounts) return 1;
    }

    struct TerminalStats {
        std::int32_t count;
        float freeClearance;
        float freeX;
        float freeY;
        float targetDistanceSquared;
    };
    using Position = std::array<float, 2>;
    struct KeyedPosition {
        std::uint64_t key;
        Position position;
    };
    const float negativeInfinity = -std::numeric_limits<float>::infinity();
    const float positiveInfinity = std::numeric_limits<float>::infinity();
    std::unordered_map<std::uint64_t, TerminalStats> terminalCache;

    const auto terminalStats = [&](float startX, float startY) {
        if (deadlineExpired()) {
            return TerminalStats{
                0,
                negativeInfinity,
                startX,
                startY,
                positiveInfinity,
            };
        }
        const std::uint64_t startKey = positionKey(startX, startY);
        const auto cached = terminalCache.find(startKey);
        if (cached != terminalCache.end()) return cached->second;

        std::vector<KeyedPosition> states{
            KeyedPosition{startKey, Position{startX, startY}}
        };
        for (
            std::int32_t startFrame = segmentLength;
            startFrame < horizon;
            startFrame += continuationLength
        ) {
            const std::int32_t endFrame = std::min(
                horizon, startFrame + continuationLength
            );
            std::vector<KeyedPosition> nextStates;
            nextStates.reserve(states.size() * kFocusedActionCount);
            for (const auto& state : states) {
                if (deadlineExpired()) {
                    return TerminalStats{
                        0,
                        negativeInfinity,
                        startX,
                        startY,
                        positiveInfinity,
                    };
                }
                for (
                    std::int32_t actionIndex = 0;
                    actionIndex < kFocusedActionCount;
                    ++actionIndex
                ) {
                    float x = state.position[0];
                    float y = state.position[1];
                    bool survived = true;
                    for (
                        std::int32_t frame = startFrame + 1;
                        frame <= endFrame;
                        ++frame
                    ) {
                        stepPlayer(
                            x,
                            y,
                            kActions[actionIndex],
                            normalSpeed,
                            focusSpeed,
                            normalDiagonalSpeed,
                            focusDiagonalSpeed
                        );
                        if (!spatialSafeAtFrame(x, y, frame - 1)) {
                            survived = false;
                            break;
                        }
                    }
                    if (survived) {
                        nextStates.push_back(KeyedPosition{
                            positionKey(x, y), Position{x, y}
                        });
                    }
                }
            }
            std::sort(
                nextStates.begin(),
                nextStates.end(),
                [](const KeyedPosition& left, const KeyedPosition& right) {
                    return left.key < right.key;
                }
            );
            nextStates.erase(
                std::unique(
                    nextStates.begin(),
                    nextStates.end(),
                    [](const KeyedPosition& left, const KeyedPosition& right) {
                        return left.key == right.key;
                    }
                ),
                nextStates.end()
            );
            if (deadlineExpired()) {
                return TerminalStats{
                    0,
                    negativeInfinity,
                    startX,
                    startY,
                    positiveInfinity,
                };
            }
            states = std::move(nextStates);
            if (states.empty()) break;
        }

        TerminalStats result{
            static_cast<std::int32_t>(states.size()),
            negativeInfinity,
            startX,
            startY,
            positiveInfinity,
        };
        if (!states.empty() && !gTerminalCountsOnly) {
            const std::int32_t terminalFrame = horizon - 1;
            for (const auto& state : states) {
                if (deadlineExpired()) {
                    return TerminalStats{
                        0,
                        negativeInfinity,
                        startX,
                        startY,
                        positiveInfinity,
                    };
                }
                const float x = state.position[0];
                const float y = state.position[1];
                float clearance = std::min({
                    x - 8.0F,
                    376.0F - x,
                    y - 16.0F,
                    432.0F - y,
                });
                for (
                    std::uint32_t index = bulletOffsets[terminalFrame];
                    index < bulletOffsets[terminalFrame + 1];
                    ++index
                ) {
                    clearance = std::min(
                        clearance,
                        signedClearance(
                            x,
                            y,
                            playerHalfWidth,
                            playerHalfHeight,
                            bullets[index]
                        )
                    );
                }
                for (
                    std::uint32_t index = laserOffsets[terminalFrame];
                    index < laserOffsets[terminalFrame + 1];
                    ++index
                ) {
                    clearance = std::min(
                        clearance,
                        signedLaserClearance(
                            x,
                            y,
                            playerHalfWidth,
                            playerHalfHeight,
                            lasers[index]
                        )
                    );
                }
                if (clearance > result.freeClearance) {
                    result.freeClearance = clearance;
                    result.freeX = x;
                    result.freeY = y;
                }
                const float targetDx = x - targetX;
                const float targetDy = y - targetY;
                result.targetDistanceSquared = std::min(
                    result.targetDistanceSquared,
                    targetDx * targetDx + targetDy * targetDy
                );
            }
        }
        terminalCache.emplace(startKey, result);
        return result;
    };

    const ControlAction current = actionFromInput(inputMask);
    for (
        std::int32_t firstIndex = 0;
        firstIndex < kControlActionCount;
        ++firstIndex
    ) {
        if (deadlineExpired()) return 1;
        terminalCountOutput[firstIndex] = 0;
        freeClearanceOutput[firstIndex] = negativeInfinity;
        freeTargetXOutput[firstIndex] = playerX;
        freeTargetYOutput[firstIndex] = playerY;
        targetDistanceSquaredOutput[firstIndex] = positiveInfinity;
        if ((candidateMask & (1U << firstIndex)) == 0U) continue;

        ControlAction transitions[5];
        const std::int32_t transitionCount = transitionActions(
            inputMask, kActionMasks[firstIndex], transitions
        );
        std::int32_t worstCount = INT32_MAX;
        float worstFreeClearance = positiveInfinity;
        float worstFreeX = playerX;
        float worstFreeY = playerY;
        float worstTargetDistanceSquared = 0.0F;
        for (const std::int32_t delay : kDelays) {
            if (deadlineExpired()) return 1;
            const std::int32_t branchCount = 1 + (
                delay > 0 ? transitionCount : 0
            );
            for (
                std::int32_t branch = 0;
                branch < branchCount;
                ++branch
            ) {
                const ControlAction* transition = branch == 0
                    ? nullptr
                    : &transitions[branch - 1];
                float x = playerX;
                float y = playerY;
                bool survived = true;
                for (
                    std::int32_t frame = 1;
                    frame <= segmentLength;
                    ++frame
                ) {
                    stepPlayer(
                        x,
                        y,
                        scheduledAction(
                            frame,
                            delay,
                            current,
                            kActions[firstIndex],
                            transition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                    if (!spatialSafeAtFrame(x, y, frame - 1)) {
                        survived = false;
                        break;
                    }
                }
                const TerminalStats branchStats = survived
                    ? terminalStats(x, y)
                    : TerminalStats{
                        0,
                        negativeInfinity,
                        x,
                        y,
                        positiveInfinity,
                    };
                if (timedOut) return 1;
                worstCount = std::min(worstCount, branchStats.count);
                if (branchStats.freeClearance < worstFreeClearance) {
                    worstFreeClearance = branchStats.freeClearance;
                    worstFreeX = branchStats.freeX;
                    worstFreeY = branchStats.freeY;
                }
                worstTargetDistanceSquared = std::max(
                    worstTargetDistanceSquared,
                    branchStats.targetDistanceSquared
                );
            }
        }
        terminalCountOutput[firstIndex] = (
            worstCount == INT32_MAX ? 0 : worstCount
        );
        freeClearanceOutput[firstIndex] = worstFreeClearance;
        freeTargetXOutput[firstIndex] = worstFreeX;
        freeTargetYOutput[firstIndex] = worstFreeY;
        targetDistanceSquaredOutput[firstIndex] = (
            worstTargetDistanceSquared
        );
    }
    return timedOut ? 1 : 0;
}

// Survival reachability consumes only the number of deduplicated terminal
// states.  Keep that computation independent from soft clearance/target
// ranking so the ordinary survival rung does not pay for unused metrics.
TH06_EXPORT std::int32_t th06_terminal_counts(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    std::int32_t* terminalCountOutput
) {
    std::array<float, kControlActionCount> freeClearanceOutput;
    std::array<float, kControlActionCount> freeTargetXOutput;
    std::array<float, kControlActionCount> freeTargetYOutput;
    std::array<float, kControlActionCount> targetDistanceSquaredOutput;
    const bool previousCountsOnly = gTerminalCountsOnly;
    gTerminalCountsOnly = true;
    const std::int32_t status = th06_terminal_guidance(
        playerX,
        playerY,
        playerHalfWidth,
        playerHalfHeight,
        normalSpeed,
        focusSpeed,
        normalDiagonalSpeed,
        focusDiagonalSpeed,
        inputMask,
        segmentLength,
        horizon,
        candidateMask,
        bulletOffsets,
        bullets,
        laserOffsets,
        lasers,
        collisionMargin,
        playerX,
        playerY,
        terminalCountOutput,
        freeClearanceOutput.data(),
        freeTargetXOutput.data(),
        freeTargetYOutput.data(),
        targetDistanceSquaredOutput.data()
    );
    gTerminalCountsOnly = previousCountsOnly;
    return status;
}

// The terminal-state result is also all-or-nothing: a timed-out soft rung
// must not publish a partial candidate ranking.
TH06_EXPORT std::int32_t th06_terminal_guidance_budgeted(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    float targetX,
    float targetY,
    double budgetMs,
    std::int32_t* terminalCountOutput,
    float* freeClearanceOutput,
    float* freeTargetXOutput,
    float* freeTargetYOutput,
    float* targetDistanceSquaredOutput
) {
    if (!(budgetMs > 0.0) || !std::isfinite(budgetMs)) return -1;
    const bool previousActive = gPolicyDeadlineActive;
    const PolicyClock::time_point previousDeadline = gPolicyDeadline;
    gPolicyDeadlineActive = true;
    gPolicyDeadline = PolicyClock::now() +
        std::chrono::duration_cast<PolicyClock::duration>(
            std::chrono::duration<double, std::milli>(budgetMs)
        );
    const std::int32_t status = th06_terminal_guidance(
        playerX,
        playerY,
        playerHalfWidth,
        playerHalfHeight,
        normalSpeed,
        focusSpeed,
        normalDiagonalSpeed,
        focusDiagonalSpeed,
        inputMask,
        segmentLength,
        horizon,
        candidateMask,
        bulletOffsets,
        bullets,
        laserOffsets,
        lasers,
        collisionMargin,
        targetX,
        targetY,
        terminalCountOutput,
        freeClearanceOutput,
        freeTargetXOutput,
        freeTargetYOutput,
        targetDistanceSquaredOutput
    );
    gPolicyDeadline = previousDeadline;
    gPolicyDeadlineActive = previousActive;
    return status;
}

// Like every budgeted proposal rung, terminal counts publish only when the
// complete candidate set finishes before the native deadline.
TH06_EXPORT std::int32_t th06_terminal_counts_budgeted(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t horizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    double budgetMs,
    std::int32_t* terminalCountOutput
) {
    if (!(budgetMs > 0.0) || !std::isfinite(budgetMs)) return -1;
    const bool previousActive = gPolicyDeadlineActive;
    const PolicyClock::time_point previousDeadline = gPolicyDeadline;
    gPolicyDeadlineActive = true;
    gPolicyDeadline = PolicyClock::now() +
        std::chrono::duration_cast<PolicyClock::duration>(
            std::chrono::duration<double, std::milli>(budgetMs)
        );
    const std::int32_t status = th06_terminal_counts(
        playerX,
        playerY,
        playerHalfWidth,
        playerHalfHeight,
        normalSpeed,
        focusSpeed,
        normalDiagonalSpeed,
        focusDiagonalSpeed,
        inputMask,
        segmentLength,
        horizon,
        candidateMask,
        bulletOffsets,
        bullets,
        laserOffsets,
        lasers,
        collisionMargin,
        terminalCountOutput
    );
    gPolicyDeadline = previousDeadline;
    gPolicyDeadlineActive = previousActive;
    return status;
}

// Progress one exact, deduplicated proposal frontier from the physical
// four-frame delivery prefix with a nominal focused choice on every later
// frame.  Each completed horizon is an all-candidate result.  If the deadline
// expires while extending the next horizon, only the last fully completed
// rung is returned; no partial layer is ever published.  Online Hard delivery
// authority remains mandatory for every action that is actually published.
TH06_EXPORT std::int32_t th06_flexible_terminal_counts_progressive(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t minimumHorizon,
    std::int32_t maximumHorizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    double budgetMs,
    std::int32_t* completedHorizonOutput,
    std::int32_t* terminalCountOutput
) {
    constexpr std::uint32_t focusedMask = (
        (1U << kFocusedActionCount) - 1U
    );
    if (
        segmentLength != 4 || minimumHorizon <= segmentLength
        || maximumHorizon < minimumHorizon || maximumHorizon > 64
        || candidateMask == 0U || (candidateMask & ~focusedMask) != 0U
        || !(budgetMs > 0.0) || !std::isfinite(budgetMs)
        || bulletOffsets == nullptr || laserOffsets == nullptr
        || completedHorizonOutput == nullptr
        || terminalCountOutput == nullptr
    ) {
        return -1;
    }

    std::fill(
        terminalCountOutput,
        terminalCountOutput + kControlActionCount,
        0
    );
    *completedHorizonOutput = 0;
    std::array<float, kControlActionCount> freeClearanceOutput;
    std::array<float, kControlActionCount> freeTargetXOutput;
    std::array<float, kControlActionCount> freeTargetYOutput;
    std::array<float, kControlActionCount> targetDistanceSquaredOutput;

    const bool previousActive = gPolicyDeadlineActive;
    const PolicyClock::time_point previousDeadline = gPolicyDeadline;
    const bool previousCountsOnly = gTerminalCountsOnly;
    const std::int32_t previousContinuationLength = (
        gTerminalContinuationLength
    );
    const std::int32_t previousMinimumHorizon = (
        gTerminalProgressiveMinimumHorizon
    );
    std::int32_t* const previousCompletedHorizon = (
        gTerminalProgressiveCompletedHorizon
    );
    gPolicyDeadlineActive = true;
    gPolicyDeadline = PolicyClock::now() +
        std::chrono::duration_cast<PolicyClock::duration>(
            std::chrono::duration<double, std::milli>(budgetMs)
        );
    gTerminalCountsOnly = true;
    gTerminalContinuationLength = 1;
    gTerminalProgressiveMinimumHorizon = minimumHorizon;
    gTerminalProgressiveCompletedHorizon = completedHorizonOutput;

    const std::int32_t status = th06_terminal_guidance(
        playerX,
        playerY,
        playerHalfWidth,
        playerHalfHeight,
        normalSpeed,
        focusSpeed,
        normalDiagonalSpeed,
        focusDiagonalSpeed,
        inputMask,
        segmentLength,
        maximumHorizon,
        candidateMask,
        bulletOffsets,
        bullets,
        laserOffsets,
        lasers,
        collisionMargin,
        playerX,
        playerY,
        terminalCountOutput,
        freeClearanceOutput.data(),
        freeTargetXOutput.data(),
        freeTargetYOutput.data(),
        targetDistanceSquaredOutput.data()
    );

    gTerminalProgressiveCompletedHorizon = previousCompletedHorizon;
    gTerminalProgressiveMinimumHorizon = previousMinimumHorizon;
    gTerminalContinuationLength = previousContinuationLength;
    gTerminalCountsOnly = previousCountsOnly;
    gPolicyDeadline = previousDeadline;
    gPolicyDeadlineActive = previousActive;

    if (status < 0) return status;
    if (*completedHorizonOutput < minimumHorizon) return 1;
    if (status == 1) return 2;
    return status;
}

// Query-local backward viability from the exact physical delivery frontier.
// Nature chooses any observed delivery/transition branch; after that branch
// is observable, the controller may choose any direction/focus action on each
// frame.  Each rung publishes only after every candidate and delivery branch
// has a complete Boolean answer.  Exact state memoization, existential
// witness short-circuiting, and monotone removal of losing first actions are
// semantic-preserving prunes rather than path-volume approximations.
TH06_EXPORT std::int32_t th06_boolean_reachability_progressive(
    float playerX,
    float playerY,
    float playerHalfWidth,
    float playerHalfHeight,
    float normalSpeed,
    float focusSpeed,
    float normalDiagonalSpeed,
    float focusDiagonalSpeed,
    std::uint16_t inputMask,
    std::int32_t segmentLength,
    std::int32_t minimumHorizon,
    std::int32_t maximumHorizon,
    std::uint32_t candidateMask,
    const std::uint32_t* bulletOffsets,
    const Aabb* bullets,
    const std::uint32_t* laserOffsets,
    const LaserHazard* lasers,
    float collisionMargin,
    double budgetMs,
    std::int32_t* completedHorizonOutput,
    std::int32_t* viabilityOutput
) {
    constexpr std::uint32_t controlMask = (
        (1U << kControlActionCount) - 1U
    );
    if (
        segmentLength != 4 || minimumHorizon <= segmentLength
        || maximumHorizon < minimumHorizon || maximumHorizon > 64
        || candidateMask == 0U || (candidateMask & ~controlMask) != 0U
        || !(budgetMs > 0.0) || !std::isfinite(budgetMs)
        || bulletOffsets == nullptr || laserOffsets == nullptr
        || completedHorizonOutput == nullptr || viabilityOutput == nullptr
    ) {
        return -1;
    }

    std::fill(
        viabilityOutput,
        viabilityOutput + kControlActionCount,
        0
    );
    *completedHorizonOutput = 0;
    const PolicyClock::time_point deadline = PolicyClock::now() +
        std::chrono::duration_cast<PolicyClock::duration>(
            std::chrono::duration<double, std::milli>(budgetMs)
        );
    const auto deadlineExpired = [&]() {
        return PolicyClock::now() >= deadline;
    };

    std::array<std::unordered_map<std::uint64_t, bool>, 64> safetyCache;
    constexpr std::int32_t kCellSize = 32;
    constexpr std::int32_t kGridWidth = 12;
    constexpr std::int32_t kGridHeight = 14;
    constexpr std::int32_t kGridCells = kGridWidth * kGridHeight;
    std::array<std::array<std::vector<std::uint32_t>, kGridCells>, 64>
        bulletGrid;
    const auto clampCellX = [](std::int32_t value) {
        return std::clamp(value, 0, kGridWidth - 1);
    };
    const auto clampCellY = [](std::int32_t value) {
        return std::clamp(value, 0, kGridHeight - 1);
    };
    for (std::int32_t frame = 0; frame < maximumHorizon; ++frame) {
        if (deadlineExpired()) return 1;
        for (
            std::uint32_t index = bulletOffsets[frame];
            index < bulletOffsets[frame + 1];
            ++index
        ) {
            const Aabb& hazard = bullets[index];
            const std::int32_t left = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.left - playerHalfWidth - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t right = clampCellX(static_cast<std::int32_t>(
                std::floor(
                    (hazard.right + playerHalfWidth + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t top = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.top - playerHalfHeight - collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            const std::int32_t bottom = clampCellY(static_cast<std::int32_t>(
                std::floor(
                    (hazard.bottom + playerHalfHeight + collisionMargin) /
                    static_cast<float>(kCellSize)
                )
            ));
            for (std::int32_t cellY = top; cellY <= bottom; ++cellY) {
                for (std::int32_t cellX = left; cellX <= right; ++cellX) {
                    bulletGrid[frame][cellY * kGridWidth + cellX].push_back(
                        index
                    );
                }
            }
        }
    }
    const auto spatialSafeAtFrame = [&](float x, float y, std::int32_t frame) {
        auto& frameCache = safetyCache[frame];
        const std::uint64_t key = positionKey(x, y);
        const auto found = frameCache.find(key);
        if (found != frameCache.end()) return found->second;
        const std::int32_t cellX = clampCellX(static_cast<std::int32_t>(
            std::floor(x / static_cast<float>(kCellSize))
        ));
        const std::int32_t cellY = clampCellY(static_cast<std::int32_t>(
            std::floor(y / static_cast<float>(kCellSize))
        ));
        bool safe = true;
        for (const std::uint32_t index : bulletGrid[frame][
            cellY * kGridWidth + cellX
        ]) {
            if (withinMargin(
                x,
                y,
                playerHalfWidth,
                playerHalfHeight,
                bullets[index],
                collisionMargin
            )) {
                safe = false;
                break;
            }
        }
        if (safe) {
            for (
                std::uint32_t index = laserOffsets[frame];
                index < laserOffsets[frame + 1];
                ++index
            ) {
                if (withinLaserMargin(
                    x,
                    y,
                    playerHalfWidth,
                    playerHalfHeight,
                    lasers[index],
                    collisionMargin
                )) {
                    safe = false;
                    break;
                }
            }
        }
        frameCache.emplace(key, safe);
        return safe;
    };

    std::array<std::vector<std::uint64_t>, kControlActionCount> branchOrigins;
    std::array<bool, kControlActionCount> prefixSafe{};
    const ControlAction current = actionFromInput(inputMask);
    for (
        std::int32_t firstIndex = 0;
        firstIndex < kControlActionCount;
        ++firstIndex
    ) {
        if ((candidateMask & (1U << firstIndex)) == 0U) continue;
        prefixSafe[firstIndex] = true;
        ControlAction transitions[5];
        const std::int32_t transitionCount = transitionActions(
            inputMask, kActionMasks[firstIndex], transitions
        );
        for (const std::int32_t delay : kDelays) {
            const std::int32_t branchCount = 1 + (
                delay > 0 ? transitionCount : 0
            );
            for (
                std::int32_t branch = 0;
                branch < branchCount;
                ++branch
            ) {
                if (deadlineExpired()) return 1;
                const ControlAction* transition = branch == 0
                    ? nullptr
                    : &transitions[branch - 1];
                float x = playerX;
                float y = playerY;
                for (
                    std::int32_t frame = 1;
                    frame <= segmentLength;
                    ++frame
                ) {
                    stepPlayer(
                        x,
                        y,
                        scheduledAction(
                            frame,
                            delay,
                            current,
                            kActions[firstIndex],
                            transition
                        ),
                        normalSpeed,
                        focusSpeed,
                        normalDiagonalSpeed,
                        focusDiagonalSpeed
                    );
                    if (!spatialSafeAtFrame(x, y, frame - 1)) {
                        prefixSafe[firstIndex] = false;
                        break;
                    }
                }
                if (!prefixSafe[firstIndex]) break;
                branchOrigins[firstIndex].push_back(positionKey(x, y));
            }
            if (!prefixSafe[firstIndex]) break;
        }
        if (prefixSafe[firstIndex]) {
            auto& origins = branchOrigins[firstIndex];
            std::sort(origins.begin(), origins.end());
            origins.erase(
                std::unique(origins.begin(), origins.end()),
                origins.end()
            );
        }
    }

    // Try focus and unfocused variants of each direction together.  This is
    // ordering only: a losing state is recorded only after all 18 successors
    // have been checked.
    constexpr std::int32_t actionOrder[kControlActionCount] = {
        0, 9, 1, 10, 2, 11, 3, 12, 4, 13,
        5, 14, 6, 15, 7, 16, 8, 17,
    };
    std::uint32_t activeMask = candidateMask;
    for (
        std::int32_t firstIndex = 0;
        firstIndex < kControlActionCount;
        ++firstIndex
    ) {
        if (
            (activeMask & (1U << firstIndex)) != 0U
            && !prefixSafe[firstIndex]
        ) {
            activeMask &= ~(1U << firstIndex);
        }
    }
    std::array<std::int32_t, kControlActionCount> lastMembership{};
    // A state that cannot reach an earlier absolute horizon cannot reach a
    // later one either. Persist those exact negative proofs across rungs.
    // Winning actions are not proofs for a deeper rung, but trying the old
    // witness first usually extends the prior policy without search churn.
    std::array<std::unordered_set<std::uint64_t>, 64> losingStates;
    std::array<std::unordered_map<std::uint64_t, std::int8_t>, 64>
        witnessActions;

    for (
        std::int32_t targetHorizon = minimumHorizon;
        targetHorizon <= maximumHorizon;
        ++targetHorizon
    ) {
        std::array<std::unordered_map<std::uint64_t, std::uint8_t>, 64> memo;
        bool timedOut = false;
        std::uint32_t deadlinePoll = 0;
        const auto canSurvive = [&](
            auto&& self,
            std::uint64_t key,
            std::int32_t frame
        ) -> bool {
            if (frame >= targetHorizon) return true;
            ++deadlinePoll;
            if (
                (deadlinePoll & 0x0FU) == 0U
                && deadlineExpired()
            ) {
                timedOut = true;
                return false;
            }
            if (losingStates[frame].count(key) != 0U) return false;
            auto& frameMemo = memo[frame];
            const auto found = frameMemo.find(key);
            if (found != frameMemo.end()) return found->second == 2U;
            float startX;
            float startY;
            positionFromKey(key, startX, startY);
            const auto tryAction = [&](std::int32_t actionIndex) {
                float x = startX;
                float y = startY;
                stepPlayer(
                    x,
                    y,
                    kActions[actionIndex],
                    normalSpeed,
                    focusSpeed,
                    normalDiagonalSpeed,
                    focusDiagonalSpeed
                );
                return spatialSafeAtFrame(x, y, frame)
                    && self(self, positionKey(x, y), frame + 1);
            };
            const auto oldWitness = witnessActions[frame].find(key);
            const std::int32_t preferredAction = (
                oldWitness == witnessActions[frame].end()
                ? -1
                : oldWitness->second
            );
            if (
                preferredAction >= 0
                && tryAction(preferredAction)
            ) {
                if (!timedOut) frameMemo.emplace(key, 2U);
                return !timedOut;
            }
            if (timedOut) return false;
            for (const std::int32_t actionIndex : actionOrder) {
                if (actionIndex == preferredAction) continue;
                if (!tryAction(actionIndex)) {
                    if (timedOut) return false;
                    continue;
                }
                witnessActions[frame][key] = static_cast<std::int8_t>(
                    actionIndex
                );
                frameMemo.emplace(key, 2U);
                return true;
            }
            frameMemo.emplace(key, 1U);
            losingStates[frame].insert(key);
            return false;
        };

        std::array<std::int32_t, kControlActionCount> rungMembership{};
        for (
            std::int32_t firstIndex = 0;
            firstIndex < kControlActionCount;
            ++firstIndex
        ) {
            if ((activeMask & (1U << firstIndex)) == 0U) continue;
            bool viable = true;
            for (const std::uint64_t origin : branchOrigins[firstIndex]) {
                if (!canSurvive(
                    canSurvive,
                    origin,
                    segmentLength
                )) {
                    viable = false;
                    break;
                }
            }
            if (timedOut) break;
            if (viable) {
                rungMembership[firstIndex] = 1;
            } else {
                // Failure at H implies failure at every H' > H.
                activeMask &= ~(1U << firstIndex);
            }
        }
        if (timedOut || deadlineExpired()) {
            return *completedHorizonOutput == 0 ? 1 : 2;
        }
        lastMembership = rungMembership;
        *completedHorizonOutput = targetHorizon;
        std::copy(
            lastMembership.begin(),
            lastMembership.end(),
            viabilityOutput
        );
        if (activeMask == 0U) {
            // The all-losing result is complete for every deeper horizon by
            // monotonicity, so no deadline-limited work remains.
            *completedHorizonOutput = maximumHorizon;
            return 0;
        }
    }
    return 0;
}
